import asyncio
import datetime
import random
from typing import Any

import discord
from discord.ext import commands, tasks

from ..config import ADMIN_DISCORD_ID
from ..logging_config import get_logger
from ..utils import (
    create_fallback_message,
    create_game_embed,
    enhance_details_with_itad,
    resolve_game_details,
    send_message,
)

logger = get_logger(__name__)


class SectorVisor(commands.Cog):
    """
    The SectorVisor Cog scans feeds for new bounties (free games) and announces them.
    """

    def __init__(self, bot):
        self.bot = bot
        self.last_check_time = None
        self.scheduled_check.start()

    async def cog_unload(self):
        self.scheduled_check.cancel()

    async def _send_admin_dm(self, message: str):
        if not ADMIN_DISCORD_ID:
            return
        try:
            user_id = int(ADMIN_DISCORD_ID)
            admin_user = await self.bot.fetch_user(user_id)
            if admin_user:
                await admin_user.send(f"SectorVisor Error: {message}")
        except ValueError:
            logger.error("Invalid ADMIN_DISCORD_ID format")
        except Exception as e:
            logger.error("Failed to send admin DM: %s", e)

    async def _process_feed(self, manual: bool = False):
        try:
            # Access scanner from bot instance
            new_announcements = await self.bot.scanner.scan()

            if not new_announcements:
                logger.info(f"Check found no new items (Manual: {manual})")
            else:
                logger.info(f"Check found {len(new_announcements)} new items (Manual: {manual})")
            await self._announce_new(new_announcements, manual=manual)
            self.last_check_time = datetime.datetime.now(datetime.UTC)
            # Update bot's last check time if needed, or keep it local.
            # The original code kept it on self.last_check_time.
            # But the 'status' command needs it. 'status' is now in Admin Cog.
            # So we should probably store it on the bot or let Admin Cog access this Cog.
            # Storing on bot is easier.
            self.bot.last_check_time = self.last_check_time

        except Exception as e:
            logger.exception("Error while processing feed: %s", e)
            await self._send_admin_dm(str(e))

    async def _announce_new(self, items: list[tuple[str, dict[str, Any]]], manual: bool = False):
        if not items:
            return
        subs = await self.bot.store.get_subscriptions()
        if not subs:
            logger.info("No subscriptions configured; skipping announcements")
            return

        for _uri, parsed in items:
            details = await resolve_game_details(self.bot, parsed)

            # Metadata Enhancement: Check ITAD for missing images
            if details:
                await enhance_details_with_itad(details, self.bot.itad_manager)

            for _guild_id, channel_id, role_id in subs:
                try:
                    channel = self.bot.get_channel(int(channel_id))
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(int(channel_id))
                        except Exception as e:
                            logger.warning(f"Could not fetch channel {channel_id}: {e}")
                            continue

                    if not isinstance(channel, discord.abc.Messageable):
                        logger.warning(f"Channel {channel_id} is not messageable")
                        continue

                    silent = role_id is None

                    if details and details.get("name") and "Unknown" not in details.get("name", "Unknown"):
                        embed = await create_game_embed(details, parsed)
                        content = f"<@&{role_id}>" if role_id else None
                        await send_message(channel, content=content, embed=embed, silent=silent)
                        logger.info(f"Sent embed for '{details.get('name')}' to channel {channel_id}")
                    else:
                        message = await create_fallback_message(parsed, role_id)
                        await send_message(channel, content=message, silent=silent)
                        logger.info(f"Sent fallback message to channel {channel_id}")
                except discord.HTTPException as e:
                    logger.error(f"Discord HTTP error sending to channel {channel_id}: {e}")
                except Exception as e:
                    logger.exception(f"Failed to send announcement to channel {channel_id}: {e}")

    # Scheduled task
    @tasks.loop(time=[datetime.time(hour=h, minute=m, tzinfo=datetime.UTC) for h in range(24) for m in (0, 30)])
    async def scheduled_check(self):
        # Add a small random delay (jitter) to avoid exact-time spikes
        await asyncio.sleep(random.uniform(1, 10))
        await self._process_feed(manual=False)

    @scheduled_check.before_loop
    async def before_scheduled_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SectorVisor(bot))
