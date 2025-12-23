import aiohttp
import discord
from discord.ext import commands, tasks

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.epic_api_manager import EpicAPIManager
from bounty_core.fetcher import BlueskyFetcher
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.itch_api_manager import ItchAPIManager
from bounty_core.parser import (
    extract_epic_slugs,
    extract_itch_urls,
    extract_links,
    extract_links_from_reddit_json,
    extract_ps_urls,
    extract_steam_ids,
    is_reddit_link,
    is_safe_link,
)
from bounty_core.ps import get_game_details as get_ps_details
from bounty_core.ps_api_manager import PSAPIManager
from bounty_core.steam import get_game_details
from bounty_core.steam_api_manager import SteamAPIManager
from bounty_core.store import Store

from .config import ADMIN_DISCORD_ID, DATABASE_PATH, POLL_INTERVAL
from .logging_config import get_logger

logger = get_logger(__name__)

SUPPORTS_SILENT = discord.version_info.major >= 2


class FreeGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = Store(DATABASE_PATH)
        self._http_session = aiohttp.ClientSession()
        self._first_run = True
        self.steam_manager = SteamAPIManager(session=self._http_session)
        self.epic_manager = EpicAPIManager(session=self._http_session)
        self.itch_manager = ItchAPIManager(session=self._http_session)
        self.ps_manager = PSAPIManager(session=self._http_session)

        if not ADMIN_DISCORD_ID:
            logger.warning("ADMIN_DISCORD_ID is not set. Admin commands and error DMs will be disabled.")

    async def cog_unload(self):
        if self._http_session:
            await self._http_session.close()

    async def _send(self, target, content=None, embed=None, silent=False):
        """Helper to send messages with optional silent flag, compatible with older discord.py."""
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if silent and SUPPORTS_SILENT:
            kwargs["silent"] = True
        return await target.send(**kwargs)

    async def _create_game_embed(self, details: dict, parsed: dict) -> discord.Embed:
        """Creates a rich embed for a game announcement."""
        color = discord.Color.green() if details.get("is_free") else discord.Color.blue()
        embed = discord.Embed(
            title=details.get("name", "Unknown Game"),
            description=parsed.get("text", ""),
            color=color,
        )
        if details.get("image"):
            embed.set_image(url=details["image"])
        if details.get("price_info"):
            embed.add_field(name="Price", value=str(details["price_info"]), inline=True)
        if details.get("release_date"):
            embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

        # Add store link
        if details.get("store_url"):
            embed.add_field(name="🎮 Store Page", value=f"[View on Store]({details['store_url']})", inline=False)

        # Improved link filtering to avoid duplicates
        def normalize_url(url: str) -> str:
            """Normalize URL for comparison by removing trailing slashes, query params, and lowercasing."""
            if not url:
                return ""
            # Remove query parameters and fragments
            url = url.split("?")[0].split("#")[0]
            # Remove trailing slashes
            url = url.rstrip("/")
            # Lowercase for comparison
            return url.lower()

        # Get normalized store URL
        store_url_norm = normalize_url(details.get("store_url", ""))

        # Build set of normalized URLs to exclude
        exclude_urls = set()
        if store_url_norm:
            exclude_urls.add(store_url_norm)

        # Add all source links to exclusion set
        source_set = set(parsed.get("source_links", []))
        for source in source_set:
            exclude_urls.add(normalize_url(source))

        # Add all store-specific URLs to exclusion set (they're already in details.store_url)
        for steam_id in parsed.get("steam_app_ids", []):
            exclude_urls.add(normalize_url(f"https://store.steampowered.com/app/{steam_id}"))
            exclude_urls.add(normalize_url(f"https://store.steampowered.com/app/{steam_id}/"))

        for epic_slug in parsed.get("epic_slugs", []):
            exclude_urls.add(normalize_url(f"https://store.epicgames.com/p/{epic_slug}"))
            exclude_urls.add(normalize_url(f"https://store.epicgames.com/en-us/p/{epic_slug}"))

        for itch_url in parsed.get("itch_urls", []):
            exclude_urls.add(normalize_url(itch_url))

        for ps_url in parsed.get("ps_urls", []):
            exclude_urls.add(normalize_url(ps_url))

        # Filter other links
        other_links = []
        seen_normalized = set()

        for link in parsed.get("links", []):
            norm_link = normalize_url(link)

            # Skip if it's a store URL, source URL, or already seen
            if norm_link in exclude_urls or norm_link in seen_normalized:
                continue

            seen_normalized.add(norm_link)
            other_links.append(link)

        # Add direct links if any (max 5, Discord field value limit)
        if other_links:
            links_text = "\n".join([f"• [Link {i + 1}]({link})" for i, link in enumerate(other_links[:5])])
            if len(other_links) > 5:
                links_text += f"\n*...and {len(other_links) - 5} more*"

            # Ensure it fits in field value limit
            if len(links_text) <= 1024:
                embed.add_field(name="🔗 Additional Links", value=links_text, inline=False)

        # Add source links (Reddit posts, etc.)
        sources = parsed.get("source_links", [])
        if sources:
            sources_text = "\n".join([f"• [Source {i + 1}]({link})" for i, link in enumerate(sources[:3])])
            if len(sources) > 3:
                sources_text += f"\n*...and {len(sources) - 3} more*"

            if len(sources_text) <= 1024:
                embed.add_field(name="📰 Sources", value=sources_text, inline=False)

        embed.set_footer(text="BountyHunter • Free Game Scout")
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

    async def _process_feed(self, manual: bool = False):
        try:
            fetcher = BlueskyFetcher(self._http_session)
            posts = await fetcher.fetch_latest()
            new_announcements = []
            for raw in posts:
                uri = raw.get("uri")
                if not uri:
                    continue
                if await self.store.is_post_seen(uri):
                    continue

                text = raw.get("record", {}).get("text", "")
                links = extract_links(raw)
                valid_links = set()
                source_links = set()

                for link in links:
                    if not is_safe_link(link):
                        continue

                    if is_reddit_link(link):
                        source_links.add(link)
                        try:
                            # If it's a shortlink, resolve it first
                            target_url = link
                            if "redd.it" in link:
                                async with self._http_session.head(link, allow_redirects=True) as resp:
                                    target_url = str(resp.url)

                            # Now append .json (handle potential query params or trailing slash)
                            # Simple approach: remove query params, ensure no slash, add .json
                            # But reddit URLs are usually clean.
                            if "?" in target_url:
                                target_url = target_url.split("?")[0]

                            json_url = target_url.rstrip("/") + ".json"

                            logger.info(f"Expanding reddit link: {link} -> {json_url}")

                            headers = {"User-Agent": "BountyHunter/1.0"}
                            async with self._http_session.get(json_url, headers=headers) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    reddit_links = extract_links_from_reddit_json(data)
                                    logger.info(f"Found {len(reddit_links)} links in reddit post")
                                    for r_link in reddit_links:
                                        if is_safe_link(r_link):
                                            valid_links.add(r_link)
                                else:
                                    logger.warning(f"Reddit expansion failed {resp.status} for {json_url}")
                        except Exception as e:
                            logger.warning(f"Failed to expand reddit link {link}: {e}")
                    else:
                        valid_links.add(link)

                if valid_links:
                    # Search for IDs in both post text and the links themselves
                    search_blob = text + " " + " ".join(valid_links)
                    steam_ids = extract_steam_ids(search_blob)
                    epic_slugs = extract_epic_slugs(search_blob)
                    itch_urls = extract_itch_urls(search_blob)
                    ps_urls = extract_ps_urls(search_blob)

                    parsed = {
                        "uri": uri,
                        "text": text,
                        "links": list(valid_links),
                        "source_links": list(source_links),
                        "steam_app_ids": list(steam_ids),
                        "epic_slugs": list(epic_slugs),
                        "itch_urls": list(itch_urls),
                        "ps_urls": list(ps_urls),
                    }
                    new_announcements.append((uri, parsed))
                    await self.store.mark_post_seen(uri)

            if not new_announcements and manual:
                logger.info("Manual check found no new items")
            await self._announce_new(new_announcements, manual=manual)
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
    @tasks.loop(minutes=POLL_INTERVAL)
    async def scheduled_check(self):
        # skip first run to avoid spam when enabling if configured to do so
        # But wait, tasks.loop runs immediately by default unless before_loop used
        # We handle first run manually
        if self._first_run:
            self._first_run = False
            return
        await self._process_feed(manual=False)

    @scheduled_check.before_loop
    async def before_scheduled_check(self):
        await self.bot.wait_until_ready()

    # Admin-only force command
    @commands.command(name="force_free")
    async def force_free_command(self, ctx: commands.Context):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return
        await ctx.send("Running free games check...")
        # Force run ignores first_run flag logic for this specific run
        await self._process_feed(manual=True)

    @commands.command(name="test_embed")
    async def test_embed_command(self, ctx: commands.Context, steam_id: str = "400"):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await self._send(ctx, "Unauthorized. Only admin may run this command.", silent=True)
            return

        await self._send(ctx, f"🔍 Generating test embed for Steam ID: `{steam_id}`...", silent=True)
        if not self.steam_manager:
            await self._send(ctx, "❌ Steam manager not initialized.", silent=True)
            return

        details = await get_game_details(steam_id, self.steam_manager, self.store)

        if not details:
            await self._send(
                ctx,
                f"❌ Could not fetch details for Steam ID `{steam_id}` (it might be invalid or hidden).",
                silent=True,
            )
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Check out this game on Steam! Great deal right now.",
            "links": [f"https://store.steampowered.com/app/{steam_id}/"],
            "source_links": ["https://reddit.com/r/GameDeals/comments/example"],
            "steam_app_ids": [steam_id],
            "epic_slugs": [],
            "itch_urls": [],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await self._send(ctx, "✅ Test embed generated:", embed=embed, silent=True)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await self._send(ctx, f"❌ Failed to create embed: {e}", silent=True)

    @commands.command(name="test_embed_epic")
    async def test_embed_epic_command(self, ctx: commands.Context, slug: str = "fortnite"):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await self._send(ctx, "Unauthorized. Only admin may run this command.", silent=True)
            return

        await self._send(ctx, f"🔍 Generating test embed for Epic Slug: `{slug}`...", silent=True)
        if not self.epic_manager:
            await self._send(ctx, "❌ Epic manager not initialized.", silent=True)
            return

        details = await get_epic_details(slug, self.epic_manager, self.store)

        if not details:
            await self._send(ctx, f"❌ Could not fetch details for Epic slug `{slug}`.", silent=True)
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game available on Epic Games Store!",
            "links": [f"https://store.epicgames.com/p/{slug}"],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [slug],
            "itch_urls": [],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await self._send(ctx, "✅ Test embed generated:", embed=embed, silent=True)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await self._send(ctx, f"❌ Failed to create embed: {e}", silent=True)

    @commands.command(name="test_embed_itch")
    async def test_embed_itch_command(self, ctx: commands.Context, url: str):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await self._send(ctx, "Unauthorized. Only admin may run this command.", silent=True)
            return

        await self._send(ctx, "🔍 Generating test embed for itch.io URL...", silent=True)
        if not self.itch_manager:
            await self._send(ctx, "❌ Itch manager not initialized.", silent=True)
            return

        details = await get_itch_details(url, self.itch_manager, self.store)

        if not details:
            await self._send(ctx, "❌ Could not fetch details for itch.io URL.", silent=True)
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game on itch.io!",
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "itch_urls": [url],
            "ps_urls": [],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await self._send(ctx, "✅ Test embed generated:", embed=embed, silent=True)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await self._send(ctx, f"❌ Failed to create embed: {e}", silent=True)

    @commands.command(name="test_embed_ps")
    async def test_embed_ps_command(self, ctx: commands.Context, url: str):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await self._send(ctx, "Unauthorized. Only admin may run this command.", silent=True)
            return

        await self._send(ctx, "🔍 Generating test embed for PlayStation Store URL...", silent=True)
        if not self.ps_manager:
            await self._send(ctx, "❌ PS manager not initialized.", silent=True)
            return

        details = await get_ps_details(url, self.ps_manager, self.store)

        if not details:
            await self._send(ctx, "❌ Could not fetch details for PlayStation Store URL.", silent=True)
            return

        # Create mock parsed data for testing
        parsed = {
            "text": "🎮 Free game on PlayStation Store!",
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "itch_urls": [],
            "ps_urls": [url],
        }

        try:
            embed = await self._create_game_embed(details, parsed)
            await self._send(ctx, "✅ Test embed generated:", embed=embed, silent=True)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await self._send(ctx, f"❌ Failed to create embed: {e}", silent=True)

    @commands.command(name="test_scraper")
    async def test_scraper_command(self, ctx: commands.Context, limit: int = 5):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await self._send(ctx, "Unauthorized. Only admin may run this command.", silent=True)
            return

        await self._send(ctx, f"🔍 Testing scraper (fetching last {limit} posts)...", silent=True)

        if not self._http_session:
            self._http_session = aiohttp.ClientSession()

        try:
            fetcher = BlueskyFetcher(self._http_session)
            posts = await fetcher.fetch_latest(limit=limit)

            if not posts:
                await self._send(ctx, "❌ No posts found.", silent=True)
                return

            await self._send(ctx, f"✅ Found {len(posts)} posts. Processing...", silent=True)

            for idx, raw in enumerate(posts, 1):
                uri = raw.get("uri")
                text = raw.get("record", {}).get("text", "")

                links = extract_links(raw)
                valid_links = set()
                source_links = set()

                for link in links:
                    if not is_safe_link(link):
                        continue

                    if is_reddit_link(link):
                        source_links.add(link)
                        try:
                            target_url = link
                            if "redd.it" in link:
                                async with self._http_session.head(link, allow_redirects=True) as resp:
                                    target_url = str(resp.url)

                            if "?" in target_url:
                                target_url = target_url.split("?")[0]
                            json_url = target_url.rstrip("/") + ".json"

                            headers = {"User-Agent": "BountyHunter/1.0"}
                            async with self._http_session.get(json_url, headers=headers) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    reddit_links = extract_links_from_reddit_json(data)
                                    for r_link in reddit_links:
                                        if is_safe_link(r_link):
                                            valid_links.add(r_link)
                        except Exception as e:
                            logger.warning(f"Failed to expand reddit link {link}: {e}")
                    else:
                        valid_links.add(link)

                if valid_links:
                    search_blob = text + " " + " ".join(valid_links)
                    steam_ids = extract_steam_ids(search_blob)
                    epic_slugs = extract_epic_slugs(search_blob)
                    itch_urls = extract_itch_urls(search_blob)
                    ps_urls = extract_ps_urls(search_blob)

                    parsed = {
                        "uri": uri,
                        "text": text,
                        "links": list(valid_links),
                        "source_links": list(source_links),
                        "steam_app_ids": list(steam_ids),
                        "epic_slugs": list(epic_slugs),
                        "itch_urls": list(itch_urls),
                        "ps_urls": list(ps_urls),
                    }

                    # Fetch details
                    details = None
                    s_ids = list(steam_ids)
                    e_slugs = list(epic_slugs)
                    i_urls = list(itch_urls)
                    p_urls = list(ps_urls)

                    if s_ids and self.steam_manager:
                        details = await get_game_details(s_ids[0], self.steam_manager, self.store)
                    elif e_slugs and self.epic_manager:
                        details = await get_epic_details(e_slugs[0], self.epic_manager, self.store)
                    elif i_urls and self.itch_manager:
                        details = await get_itch_details(i_urls[0], self.itch_manager, self.store)
                    elif p_urls and self.ps_manager:
                        details = await get_ps_details(p_urls[0], self.ps_manager, self.store)

                    # Send result
                    await self._send(ctx, f"\n**Post {idx}/{len(posts)}:**", silent=True)

                    if details and "Unknown" not in details.get("name", "Unknown"):
                        try:
                            embed = await self._create_game_embed(details, parsed)
                            await self._send(ctx, embed=embed, silent=True)
                        except Exception as e:
                            logger.exception(f"Failed to create embed: {e}")
                            fallback = await self._create_fallback_message(parsed, None)
                            await self._send(ctx, fallback, silent=True)
                    else:
                        fallback = await self._create_fallback_message(parsed, None)
                        await self._send(ctx, fallback, silent=True)
                else:
                    await self._send(
                        ctx,
                        f"**Post {idx}/{len(posts)}:** No valid game links found",
                        silent=True,
                    )

            await self._send(ctx, "✅ Scraper test complete.", silent=True)

        except Exception as e:
            logger.exception("Scraper test failed: %s", e)
            await self._send(ctx, f"❌ Scraper test failed: {e}", silent=True)

    @commands.command(name="myid")
    async def myid_command(self, ctx: commands.Context):
        await self._send(ctx, f"Your ID: `{ctx.author.id}`", silent=True)

    # Subscribe command (requires Manage Guild)
    @commands.command(name="subscribe")
    @commands.has_permissions(manage_guild=True)
    async def subscribe_command(self, ctx: commands.Context, role: discord.Role | None = None):
        try:
            if not ctx.guild:
                await ctx.send("Subscription only works within a guild.")
                return

            role_id = role.id if role else None
            await self.store.add_subscription(ctx.guild.id, ctx.channel.id, role_id)

            msg = "This channel is subscribed to free-game announcements."
            if role:
                msg += f" I will ping {role.mention}."
            await ctx.send(msg)
        except Exception as e:
            logger.exception("subscribe failed: %s", e)
            await ctx.send("Failed to subscribe. See logs.")

    @subscribe_command.error
    async def subscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Manage Guild permission to run this.")

    @commands.command(name="unsubscribe")
    @commands.has_permissions(manage_guild=True)
    async def unsubscribe_command(self, ctx: commands.Context):
        try:
            if not ctx.guild:
                await ctx.send("Unsubscribe only works within a guild.")
                return
            await self.store.remove_subscription(ctx.guild.id, ctx.channel.id)
            await ctx.send("This channel has been unsubscribed.")
        except Exception as e:
            logger.exception("unsubscribe failed: %s", e)
            await ctx.send("Failed to unsubscribe. See logs.")

    @unsubscribe_command.error
    async def unsubscribe_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Manage Guild permission to run this.")
