import asyncio
import os
from interactions import Extension, Client, IntervalTrigger, Task, listen, Embed, Color
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import aiohttp
from free_games_core.fetcher import fetch_bsky_feed, extract_links_from_text
from free_games_core.parser import parse_post_for_links
from free_games_core.store import Store
from free_games_core.steam import fetch_game_details
from .config import BOT_TOKEN, DATABASE_PATH, POLL_INTERVAL, ADMIN_DISCORD_ID
from .logging_config import get_logger

logger = get_logger(__name__)

class FreeGames(Extension):
    def __init__(self, bot: Client):
        self.bot = bot
        self.store = Store(db_path=DATABASE_PATH)
        self._http_session: aiohttp.ClientSession | None = None
        self._first_run = True

    async def on_load(self):
        await self.store.init()
        self._http_session = aiohttp.ClientSession()
        logger.info("FreeGames extension loaded")

    async def on_unload(self):
        if self._http_session:
            await self._http_session.close()
        await self.store.close()

    async def _send_admin_dm(self, message: str):
        try:
            if ADMIN_DISCORD_ID:
                admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
                if admin_user:
                    await admin_user.send(f"FreeGames Error: {message}")
        except Exception as e:
            logger.error("Failed to send admin DM: %s", e)

    async def _process_feed(self, manual: bool = False):
        if not self._http_session:
            self._http_session = aiohttp.ClientSession()
        try:
            posts = await fetch_bsky_feed(self._http_session)
            new_announcements = []
            for raw in posts:
                parsed = parse_post_for_links(raw)
                uri = parsed.get("uri")
                if not uri:
                    continue
                if await self.store.seen(uri):
                    continue
                # For now we treat any post with links as a candidate
                if parsed.get("links"):
                    new_announcements.append((uri, parsed))
                    await self.store.mark_seen(uri)

            if not new_announcements and manual:
                logger.info("Manual check found no new items")
            await self._announce_new(new_announcements, manual=manual)
        except Exception as e:
            logger.exception("Error while processing feed: %s", e)
            await self._send_admin_dm(str(e))

    async def _announce_new(self, items, manual=False):
        if not items:
            return
        # Send to all subscriptions
        subs = await self.store.list_subscriptions()
        if not subs:
            logger.info("No subscriptions configured; skipping announcements")
            return

        messages = []
        for uri, parsed in items:
            title = parsed.get("text", "")[:250] or "New free game"
            # If steam ids exist, fetch details for nicer embedding
            steam_ids = parsed.get("steam_app_ids", [])
            details = None
            if steam_ids:
                details = await fetch_game_details(steam_ids[0])

            embed = Embed(
                title=details["name"] if details else title,
                description=parsed.get("text"),
                color=Color.DEFAULT,
            )
            if details and details.get("store_url"):
                embed.add_field(name="Store", value=details["store_url"], inline=False)
            messages.append((embed, parsed.get("links")))

        # iterate subs and send
        for guild_id, channel_id in subs:
            for embed, links in messages:
                try:
                    await self.bot.create_message(channel_id, embeds=embed)
                except Exception as e:
                    logger.exception("Failed to send announcement to %s: %s", channel_id, e)

    # Scheduled task
    @Task.create(IntervalTrigger(minutes=POLL_INTERVAL))
    async def scheduled_check(self):
        # skip first run to avoid spam when enabling
        if self._first_run:
            self._first_run = False
            return
        await self._process_feed(manual=False)

    # Admin-only force command
    @prefixed_command(name="force_free")
    async def force_free_command(self, ctx: PrefixedContext):
        if ADMIN_DISCORD_ID and str(ctx.author_id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return
        await ctx.send("Running free games check...")
        original_first = self._first_run
        self._first_run = False
        await self._process_feed(manual=True)
        self._first_run = original_first

    # Subscribe command (requires Manage Guild)
    @prefixed_command(name="subscribe")
    async def subscribe_command(self, ctx: PrefixedContext):
        try:
            if not ctx.guild_id:
                await ctx.send("Subscription only works within a guild.")
                return
            # You might want to check permissions; for now check Manage Guild capability
            member = await ctx.get_guild_member()
            perms = member.permissions  # integer bitfield
            # interactions permissions: 0x20 = Manage Guild (32)
            if not (perms & 0x20):
                await ctx.send("You need Manage Guild permission to run this.")
                return
            await self.store.add_subscription(ctx.guild_id, ctx.channel_id)
            await ctx.send("This channel is subscribed to free-game announcements.")
        except Exception as e:
            logger.exception("subscribe failed: %s", e)
            await ctx.send("Failed to subscribe. See logs.")

    @prefixed_command(name="unsubscribe")
    async def unsubscribe_command(self, ctx: PrefixedContext):
        try:
            if not ctx.guild_id:
                await ctx.send("Unsubscribe only works within a guild.")
                return
            member = await ctx.get_guild_member()
            perms = member.permissions
            if not (perms & 0x20):
                await ctx.send("You need Manage Guild permission to run this.")
                return
            await self.store.remove_subscription(ctx.guild_id, ctx.channel_id)
            await ctx.send("This channel has been unsubscribed.")
        except Exception as e:
            logger.exception("unsubscribe failed: %s", e)
            await ctx.send("Failed to unsubscribe. See logs.")