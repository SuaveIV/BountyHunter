import asyncio
import datetime
import logging
import random

import aiohttp
import discord
from discord.ext import commands, tasks

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.epic_api_manager import EpicAPIManager
from bounty_core.fetcher import TARGET_ACTOR, RedditRSSFetcher
from bounty_core.itad_api_manager import ItadAPIManager
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.itch_api_manager import ItchAPIManager
from bounty_core.parser import determine_content_type, extract_game_title
from bounty_core.ps import get_game_details as get_ps_details
from bounty_core.ps_api_manager import PSAPIManager
from bounty_core.steam import get_game_details
from bounty_core.steam_api_manager import SteamAPIManager
from bounty_core.store import Store
from bounty_discord.modules.sector_scanner import SectorScanner

from .config import ADMIN_DISCORD_ID, DATABASE_PATH, ITAD_API_KEY
from .logging_config import get_logger

logger = get_logger(__name__)

SUPPORTS_SILENT = discord.version_info.major >= 2


def is_admin_dm():
    """Check if the command is invoked by the admin in a DM channel."""

    async def predicate(ctx):
        if not ADMIN_DISCORD_ID:
            return False
        if str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            return False
        if not isinstance(ctx.channel, discord.DMChannel):
            return False
        return True

    return commands.check(predicate)


class DiscordLoggingHandler(logging.Handler):
    """Custom logging handler to send Critical errors to the Admin via DM."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.setLevel(logging.CRITICAL)

    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.bot.loop.create_task(self.send_dm(log_entry))
        except Exception:
            pass

    async def send_dm(self, message):
        if not ADMIN_DISCORD_ID:
            return
        try:
            user = await self.bot.fetch_user(int(ADMIN_DISCORD_ID))
            if user:
                if len(message) > 1900:
                    message = message[:1900] + "..."
                await user.send(f"🚨 **CRITICAL ERROR** 🚨\n```\n{message}\n```")
        except Exception:
            pass


class FreeGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = Store(DATABASE_PATH)
        self._http_session = aiohttp.ClientSession()
        self.start_time = datetime.datetime.now(datetime.UTC)
        self.last_check_time = None
        self.steam_manager = SteamAPIManager(session=self._http_session)
        self.epic_manager = EpicAPIManager(session=self._http_session)
        self.itch_manager = ItchAPIManager(session=self._http_session)
        self.ps_manager = PSAPIManager(session=self._http_session)
        self.itad_manager = ItadAPIManager(session=self._http_session, api_key=ITAD_API_KEY)
        self.scanner = SectorScanner(RedditRSSFetcher(self._http_session), self.store)

        # Setup Critical Error Logging to DM
        self.log_handler = DiscordLoggingHandler(bot)
        self.log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)

        # Start the scheduled check loop
        self.scheduled_check.start()

        if not ADMIN_DISCORD_ID:
            logger.warning("ADMIN_DISCORD_ID is not set. Admin commands and error DMs will be disabled.")

    async def cog_unload(self):
        logging.getLogger().removeHandler(self.log_handler)
        if self._http_session:
            await self._http_session.close()

    async def _send(self, target, content=None, embed=None, silent=False):
        """Helper to send messages with optional silent flag, compatible with older discord.py."""
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if silent:
            kwargs["allowed_mentions"] = discord.AllowedMentions.none()
            if SUPPORTS_SILENT:
                kwargs["silent"] = True
        return await target.send(**kwargs)

    async def _create_game_embed(self, details: dict, parsed: dict) -> discord.Embed:
        """Creates a rich embed for a game announcement, matching FamilyBot style."""
        store_url = details.get("store_url", parsed.get("links", [""])[0])

        # Determine store type
        is_steam = "store.steampowered.com" in store_url
        is_epic = "store.epicgames.com" in store_url
        is_itch = "itch.io" in store_url
        is_gog = "gog.com" in store_url
        is_ps = "store.playstation.com" in store_url
        is_amazon = "amazon.com" in store_url or "gaming.amazon.com" in store_url
        is_stove = "stove.com" in store_url or "onstove.com" in store_url

        # Determine prefix based on parsed type
        post_type = parsed.get("type", "UNKNOWN")
        if post_type == "GAME":
            title_prefix = "FREE GAME"
        elif post_type == "ITEM":
            title_prefix = "FREE ITEM"
        else:
            title_prefix = "FREE"

        embed = discord.Embed()
        embed.title = f"{title_prefix}: {details.get('name', 'Unknown Game')}"
        embed.url = store_url

        # Footer keeps BountyHunter branding but dynamic TARGET_ACTOR
        embed.set_footer(text=f"BountyHunter • Free Game Scout • {TARGET_ACTOR}")

        if is_steam:
            embed.color = discord.Color.from_str("#00FF00")  # Green
            embed.description = details.get("short_description", parsed.get("text", "")) or "No description available."

            if details.get("image"):
                embed.set_image(url=details["image"])

            # Price Info
            price_info = details.get("price_info")
            if isinstance(price_info, dict):
                original = price_info.get("original_price", "N/A")
                discount = price_info.get("discount_percent", 0)
                embed.add_field(name="Price", value=f"~~{original}~~ -> FREE ({discount}% off)", inline=True)
            elif isinstance(price_info, str):
                embed.add_field(name="Price", value=price_info, inline=True)

            # Reviews
            if details.get("review_summary"):
                embed.add_field(name="Reviews", value=details["review_summary"], inline=True)

            # Release Date
            if details.get("release_date"):
                embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

            # Creators
            developers = details.get("developers", [])
            publishers = details.get("publishers", [])
            if developers or publishers:
                dev_str = ", ".join(developers) if developers else "N/A"
                pub_str = ", ".join(publishers) if publishers else "N/A"
                embed.add_field(name="Creator(s)", value=f"**Dev:** {dev_str}\n**Pub:** {pub_str}", inline=True)

        elif is_epic:
            embed.color = discord.Color.from_str("#0078F2")  # Epic Blue
            embed.description = "Claim this game for free on the Epic Games Store!"
            embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2699/PNG/128/epic_games_logo_icon_169084.png")
            embed.add_field(name="Platform", value="Epic Games Store", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        elif is_itch:
            embed.color = discord.Color.from_str("#FA5C5C")  # Itch Pink
            embed.description = "Claim this game for free on Itch.io!"
            embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2428/PNG/512/itch_io_logo_icon_147227.png")
            embed.add_field(name="Platform", value="Itch.io", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        elif is_gog:
            embed.color = discord.Color.from_str("#8A4399")  # GOG Purple
            embed.description = "Claim this game for free on GOG.com!"
            embed.set_thumbnail(url="https://cdn.icon-icons.com/icons2/2428/PNG/512/gog_logo_icon_147232.png")
            embed.add_field(name="Platform", value="GOG.com", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        elif is_amazon:
            embed.color = discord.Color.from_str("#00A8E1")  # Amazon Blue
            embed.description = "Claim this game for free with Amazon Prime Gaming!"
            embed.set_thumbnail(
                url="https://cdn.icon-icons.com/icons2/2699/PNG/128/amazon_prime_gaming_logo_icon_169083.png"
            )
            embed.add_field(name="Platform", value="Amazon Prime Gaming", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        elif is_ps:
            embed.color = discord.Color.blue()
            embed.description = "Claim this game for free on the PlayStation Store!"
            embed.add_field(name="Platform", value="PlayStation Store", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        elif is_stove:
            embed.color = discord.Color.from_str("#FF6B00")  # STOVE Orange
            embed.description = "Claim this game for free on STOVE!"
            embed.add_field(name="Platform", value="STOVE", inline=True)
            if details.get("image"):
                embed.set_image(url=details["image"])

        else:
            # Fallback for generic sites
            embed.color = discord.Color.green()
            # If description is not provided in details, use text
            embed.description = details.get("description") or parsed.get("text", "Free game announcement")
            if details.get("image"):
                embed.set_image(url=details["image"])

        # Retain original link logic for "Additional Links" and "Sources"
        def normalize_url(url: str) -> str:
            if not url:
                return ""
            return url.split("?")[0].split("#")[0].rstrip("/").lower()

        exclude_urls = {normalize_url(store_url)}
        source_set = set(parsed.get("source_links", []))
        for source in source_set:
            exclude_urls.add(normalize_url(source))

        other_links = []
        seen_normalized = set()
        for link in parsed.get("links", []):
            norm_link = normalize_url(link)
            if norm_link in exclude_urls or norm_link in seen_normalized:
                continue
            seen_normalized.add(norm_link)
            other_links.append(link)

        if other_links:
            links_text = "\n".join([f"• [Link {i + 1}]({link})" for i, link in enumerate(other_links[:5])])
            if len(other_links) > 5:
                links_text += f"\n*...and {len(other_links) - 5} more*"
            if len(links_text) <= 1024:
                embed.add_field(name="🔗 Additional Links", value=links_text, inline=False)

        if source_set:
            sources = list(source_set)
            sources_text = "\n".join([f"• [Source {i + 1}]({link})" for i, link in enumerate(sources[:3])])
            if len(sources) > 3:
                sources_text += f"\n*...and {len(sources) - 3} more*"
            if len(sources_text) <= 1024:
                embed.add_field(name="📰 Sources", value=sources_text, inline=False)

        return embed

    async def _create_fallback_message(self, parsed: dict, role_id: int | None) -> str:
        text = parsed.get("text", "")
        links = parsed.get("links", [])
        source_links = parsed.get("source_links", [])
        content = text
        all_links = links + source_links
        for link in all_links:
            if link not in content:
                content += f"\n{link}"
        if role_id:
            content = f"<@&{role_id}>\n{content}"
        return content

    async def _send_admin_dm(self, message: str):
        if not ADMIN_DISCORD_ID:
            return
        try:
            user_id = int(ADMIN_DISCORD_ID)
            admin_user = await self.bot.fetch_user(user_id)
            if admin_user:
                await admin_user.send(f"FreeGames Error: {message}")
        except ValueError:
            logger.error("Invalid ADMIN_DISCORD_ID format")
        except Exception as e:
            logger.error("Failed to send admin DM: %s", e)

    async def _get_fallback_details(self, links: list[str], text: str, image: str | None = None) -> dict:
        fallback_url = None
        for link in links:
            if any(d in link for d in ["gog.com", "amazon.com", "onstove.com", "stove.com"]):
                fallback_url = link
                break
        if not fallback_url and links:
            fallback_url = links[0]

        if not fallback_url:
            return {}

        title = extract_game_title(text) or "Free Game"

        # Heuristic: if title wasn't extracted and text is short, assume text is the title
        if title == "Free Game" and text and len(text) < 50 and "http" not in text:
            title = text

        details = {
            "name": title,
            "store_url": fallback_url,
            "image": image,
        }

        # Try to fetch image from ITAD if missing
        if not details["image"] and title != "Free Game" and self.itad_manager and ITAD_API_KEY:
            try:
                results = await self.itad_manager.search_game(title, limit=1)
                if results:
                    game_info = results[0]
                    assets = game_info.get("assets", {})
                    banner = assets.get("banner400") or assets.get("banner300") or assets.get("boxArt")
                    if banner:
                        details["image"] = banner
                        logger.info(f"Fetched image for '{title}' from ITAD")
            except Exception as e:
                logger.warning(f"Failed to fetch ITAD image for '{title}': {e}")

        return details

    async def _process_feed(self, manual: bool = False):
        try:
            new_announcements = await self.scanner.scan()

            if not new_announcements:
                logger.info(f"Check found no new items (Manual: {manual})")
            else:
                logger.info(f"Check found {len(new_announcements)} new items (Manual: {manual})")
            await self._announce_new(new_announcements, manual=manual)
            self.last_check_time = datetime.datetime.now(datetime.UTC)
        except Exception as e:
            logger.exception("Error while processing feed: %s", e)
            await self._send_admin_dm(str(e))

    async def _announce_new(self, items, manual=False):
        if not items:
            return
        subs = await self.store.get_subscriptions()
        if not subs:
            logger.info("No subscriptions configured; skipping announcements")
            return

        for _uri, parsed in items:
            steam_ids = parsed.get("steam_app_ids", [])
            epic_slugs = parsed.get("epic_slugs", [])
            itch_urls = parsed.get("itch_urls", [])
            ps_urls = parsed.get("ps_urls", [])

            details = None
            if steam_ids and self.steam_manager:
                details = await get_game_details(steam_ids[0], self.steam_manager, self.store)
            elif epic_slugs and self.epic_manager:
                details = await get_epic_details(epic_slugs[0], self.epic_manager, self.store)
            elif itch_urls and self.itch_manager:
                details = await get_itch_details(itch_urls[0], self.itch_manager, self.store)
            elif ps_urls and self.ps_manager:
                details = await get_ps_details(ps_urls[0], self.ps_manager, self.store)

            # Fallback: use generic details if specific manager didn't handle it
            if not details and parsed.get("links"):
                details = await self._get_fallback_details(parsed["links"], parsed["text"], image=parsed.get("image"))

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
                        embed = await self._create_game_embed(details, parsed)
                        content = f"<@&{role_id}>" if role_id else None
                        await self._send(channel, content=content, embed=embed, silent=silent)
                        logger.info(f"Sent embed for '{details.get('name')}' to channel {channel_id}")
                    else:
                        message = await self._create_fallback_message(parsed, role_id)
                        await self._send(channel, content=message, silent=silent)
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

    # --- Admin DM Commands ---

    @commands.command(name="force_free")
    @is_admin_dm()
    async def force_free(self, ctx: commands.Context):
        """Force run the free games check (Admin DM only)."""
        await ctx.send("Running free games check...")
        # Force run ignores first_run flag logic for this specific run
        await self._process_feed(manual=True)

    @commands.command(name="test_embed")
    @is_admin_dm()
    async def test_embed(self, ctx: commands.Context, steam_id: str = "400"):
        """Generate a test embed for a Steam ID (Admin DM only)."""
        await ctx.send(f"🔍 Generating test embed for Steam ID: `{steam_id}`...")
        if not self.steam_manager:
            await ctx.send("❌ Steam manager not initialized.")
            return

        details = await get_game_details(steam_id, self.steam_manager, self.store)

        if not details:
            await ctx.send(f"❌ Could not fetch details for Steam ID `{steam_id}` (it might be invalid or hidden).")
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Check out this game on Steam! Great deal right now.",
            "type": "GAME",
            "links": [f"https://store.steampowered.com/app/{steam_id}/"],
            "source_links": ["https://reddit.com/r/GameDeals/comments/example"],
            "steam_app_ids": [steam_id],
            "epic_slugs": [],
            "itch_urls": [],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_epic")
    @is_admin_dm()
    async def test_embed_epic(self, ctx: commands.Context, slug: str = "fortnite"):
        """Generate a test embed for an Epic Games slug (Admin DM only)."""
        await ctx.send(f"🔍 Generating test embed for Epic Slug: `{slug}`...")
        if not self.epic_manager:
            await ctx.send("❌ Epic manager not initialized.")
            return

        details = await get_epic_details(slug, self.epic_manager, self.store)

        if not details:
            await ctx.send(f"❌ Could not fetch details for Epic slug `{slug}`.")
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game available on Epic Games Store!",
            "type": "GAME",
            "links": [f"https://store.epicgames.com/p/{slug}"],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [slug],
            "itch_urls": [],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_itch")
    @is_admin_dm()
    async def test_embed_itch(self, ctx: commands.Context, url: str):
        """Generate a test embed for an itch.io URL (Admin DM only)."""
        await ctx.send("🔍 Generating test embed for itch.io URL...")
        if not self.itch_manager:
            await ctx.send("❌ Itch manager not initialized.")
            return

        details = await get_itch_details(url, self.itch_manager, self.store)

        if not details:
            await ctx.send("❌ Could not fetch details for itch.io URL.")
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game on itch.io!",
            "type": "GAME",
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "itch_urls": [url],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_ps")
    @is_admin_dm()
    async def test_embed_ps(self, ctx: commands.Context, url: str):
        """Generate a test embed for a PlayStation Store URL (Admin DM only)."""
        await ctx.send("🔍 Generating test embed for PlayStation Store URL...")
        if not self.ps_manager:
            await ctx.send("❌ PS manager not initialized.")
            return

        details = await get_ps_details(url, self.ps_manager, self.store)

        if not details:
            await ctx.send("❌ Could not fetch details for PlayStation Store URL.")
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game on PlayStation Store!",
            "type": "GAME",
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "itch_urls": [],
            "ps_urls": [url],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_url")
    @is_admin_dm()
    async def test_embed_url(self, ctx: commands.Context, url: str, *, text: str = "Free Game Announcement"):
        """
        Generate a test embed for any URL (GOG, Amazon, Stove, etc.).
        Usage: !test_embed_url <url> [optional text simulating the post]
        """
        await ctx.send(f"🔍 Generating test embed for URL: `{url}`...")

        # Create mock parsed data
        parsed = {
            "text": text,
            "type": determine_content_type(text),
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "itch_urls": [],
            "ps_urls": [],
        }

        # Use centralized fallback logic (which also checks ITAD for images)
        details = await self._get_fallback_details([url], text, image=None)

        try:
            embed = await self._create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_all")
    @is_admin_dm()
    async def test_embed_all(self, ctx: commands.Context):
        """Generate example embeds for all supported stores."""
        await ctx.send("🚀 Generating example embeds for all supported stores...")

        # 1. Steam (Portal)
        await self.test_embed(ctx, steam_id="400")

        # 2. Epic (Fortnite)
        await self.test_embed_epic(ctx, slug="fortnite")

        # 3. Itch.io (Deltarune)
        await self.test_embed_itch(ctx, url="https://tobyfox.itch.io/deltarune")

        # 4. GOG
        await self.test_embed_url(
            ctx, url="https://www.gog.com/en/game/cyberpunk_2077", text="[GOG] Cyberpunk 2077 is free on GOG!"
        )

        # 5. Amazon Prime
        await self.test_embed_url(
            ctx, url="https://gaming.amazon.com/loot/fallout", text="[Prime] Fallout 76 is free with Prime Gaming!"
        )

        # 6. STOVE
        await self.test_embed_url(
            ctx,
            url="https://store.onstove.com/en/games/1234",
            text="[STOVE] SNK 40th Anniversary Collection is free on STOVE!",
        )

        # 7. PlayStation (Generic fallback as we don't have a stable ID for scraping)
        await self.test_embed_url(
            ctx,
            url="https://store.playstation.com/en-us/product/UP9000-CUSA00917_00-THELASTOFUS00000",
            text="[PS4] The Last of Us Remastered is free!",
        )

        await ctx.send("✅ All examples generated.")

    @commands.command(name="test_scraper")
    @is_admin_dm()
    async def test_scraper(self, ctx: commands.Context, limit: int = 5):
        """Test the scraper feed (Admin DM only)."""
        await ctx.send(f"🔍 Testing scraper (fetching last {limit} posts)...")

        try:
            # Use scanner with ignore_seen=True to preview posts without marking them
            posts = await self.scanner.scan(limit=limit, ignore_seen=True)

            if not posts:
                await ctx.send("❌ No posts found.")
                return

            await ctx.send(f"✅ Found {len(posts)} posts. Processing...")

            for idx, (_uri, parsed) in enumerate(posts, 1):
                # Fetch details
                details = None
                s_ids = parsed.get("steam_app_ids", [])
                e_slugs = parsed.get("epic_slugs", [])
                i_urls = parsed.get("itch_urls", [])
                p_urls = parsed.get("ps_urls", [])

                if s_ids and self.steam_manager:
                    details = await get_game_details(s_ids[0], self.steam_manager, self.store)
                elif e_slugs and self.epic_manager:
                    details = await get_epic_details(e_slugs[0], self.epic_manager, self.store)
                elif i_urls and self.itch_manager:
                    details = await get_itch_details(i_urls[0], self.itch_manager, self.store)
                elif p_urls and self.ps_manager:
                    details = await get_ps_details(p_urls[0], self.ps_manager, self.store)

                # Fallback logic for test_scraper
                if not details and parsed.get("links"):
                    details = await self._get_fallback_details(
                        parsed["links"], parsed["text"], image=parsed.get("image")
                    )

                # Send result
                await ctx.send(f"\n**Post {idx}/{len(posts)}:**")

                if details and "Unknown" not in details.get("name", "Unknown"):
                    try:
                        embed = await self._create_game_embed(details, parsed)
                        await ctx.send(embed=embed)
                    except Exception as e:
                        logger.exception(f"Failed to create embed: {e}")
                        fallback = await self._create_fallback_message(parsed, None)
                        await ctx.send(fallback)
                else:
                    fallback = await self._create_fallback_message(parsed, None)
                    await ctx.send(fallback)

            await ctx.send("✅ Scraper test complete.")

        except Exception as e:
            logger.exception("Scraper test failed: %s", e)
            await ctx.send(f"❌ Scraper test failed: {e}")

    @commands.command(name="clear_cache")
    @is_admin_dm()
    async def clear_cache(self, ctx: commands.Context):
        """Clear all game caches (Admin DM only)."""
        await ctx.send("🧹 Clearing game caches...")
        try:
            await self.store.clear_cache()
            await ctx.send("✅ Cache cleared. Re-run tests to fetch fresh data.")
        except Exception as e:
            logger.exception(f"Failed to clear cache: {e}")
            await ctx.send(f"❌ Failed to clear cache: {e}")

    @commands.command(name="status")
    @is_admin_dm()
    async def status(self, ctx: commands.Context):
        """Show bot uptime and last check time (Admin DM only)."""
        now = datetime.datetime.now(datetime.UTC)
        uptime = now - self.start_time

        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        last_check = f"<t:{int(self.last_check_time.timestamp())}:R>" if self.last_check_time else "Never"

        embed = discord.Embed(title="Bot Status", color=discord.Color.teal())
        embed.add_field(name="⏱️ Uptime", value=uptime_str, inline=True)
        embed.add_field(name="🔄 Last Check", value=last_check, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="myid")
    @is_admin_dm()
    async def myid(self, ctx: commands.Context):
        """Get your Discord ID (Admin DM only)."""
        await ctx.send(f"Your ID: `{ctx.author.id}`")

    @commands.command(name="price")
    async def check_price(self, ctx: commands.Context, *, title: str):
        """Check price of a game using IsThereAnyDeal."""
        await ctx.send(f"🔍 Checking price for `{title}`...")

        if not ITAD_API_KEY:
            await ctx.send("❌ ITAD API Key is not configured.")
            return

        result = await self.itad_manager.get_best_price(title)
        if not result:
            await ctx.send("❌ Game not found or no price info available.")
            return

        game = result["game_info"]
        price = result["price_info"]

        current = price.get("current")
        lowest = price.get("lowest")

        embed = discord.Embed(title=game.get("title", title), url=price["urls"]["game"])
        assets = game.get("assets", {})
        if assets and assets.get("banner400"):
            embed.set_image(url=assets["banner400"])

        if current:
            shop_name = current.get("shop", {}).get("name", "Unknown")
            amount = current.get("price", {}).get("amount", 0)
            currency = current.get("price", {}).get("currency", "USD")
            url = current.get("url", "")
            embed.add_field(
                name="Current Best Price",
                value=f"**{amount} {currency}** at [{shop_name}]({url})",
                inline=False,
            )

        if lowest:
            shop_name = lowest.get("shop", {}).get("name", "Unknown")
            amount = lowest.get("price", {}).get("amount", 0)
            currency = lowest.get("price", {}).get("currency", "USD")
            timestamp = lowest.get("timestamp", "")
            embed.add_field(
                name="Historical Low",
                value=f"{amount} {currency} at {shop_name} ({timestamp})",
                inline=False,
            )

        embed.set_footer(text="Powered by IsThereAnyDeal")
        await ctx.send(embed=embed)

    # --- Guild Commands ---

    @commands.command(name="subscribe")
    @commands.has_permissions(manage_guild=True)
    async def subscribe_command(self, ctx: commands.Context, role: discord.Role | None = None):
        """Subscribe the current channel to free game announcements (Guild only)."""
        try:
            if not ctx.guild:
                await ctx.send("Subscription only works within a guild.")
                return

            role_id = role.id if role else None
            await self.store.add_subscription(ctx.guild.id, ctx.channel.id, role_id)

            msg = "This channel is subscribed to free-game announcements."
            if role:
                msg += f" I will ping {role.mention}."
            await self._send(ctx, msg, silent=True)
        except Exception as e:
            logger.exception("subscribe failed: %s", e)
            await self._send(ctx, "Failed to subscribe. See logs.", silent=True)

    @subscribe_command.error
    async def subscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._send(ctx, "You need Manage Guild permission to run this.", silent=True)

    @commands.command(name="unsubscribe")
    @commands.has_permissions(manage_guild=True)
    async def unsubscribe_command(self, ctx: commands.Context):
        """Unsubscribe the current channel from free game announcements (Guild only)."""
        try:
            if not ctx.guild:
                await ctx.send("Unsubscribe only works within a guild.")
                return
            await self.store.remove_subscription(ctx.guild.id, ctx.channel.id)
            await self._send(ctx, "This channel has been unsubscribed.", silent=True)
        except Exception as e:
            logger.exception("unsubscribe failed: %s", e)
            await self._send(ctx, "Failed to unsubscribe. See logs.", silent=True)

    @unsubscribe_command.error
    async def unsubscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._send(ctx, "You need Manage Guild permission to run this.", silent=True)
