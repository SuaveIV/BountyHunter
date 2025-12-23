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


class FreeGames(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = Store(db_path=DATABASE_PATH)
        self._http_session: aiohttp.ClientSession | None = None
        self.steam_manager: SteamAPIManager | None = None
        self.epic_manager: EpicAPIManager | None = None
        self.itch_manager: ItchAPIManager | None = None
        self.ps_manager: PSAPIManager | None = None
        self._first_run = True

    async def cog_load(self):
        await self.store.setup()
        self._http_session = aiohttp.ClientSession()
        self.steam_manager = SteamAPIManager(self._http_session)
        self.epic_manager = EpicAPIManager(self._http_session)
        self.itch_manager = ItchAPIManager(self._http_session)
        self.ps_manager = PSAPIManager(self._http_session)
        self.scheduled_check.start()
        logger.info("FreeGames extension loaded")

    async def cog_unload(self):
        self.scheduled_check.cancel()
        if self._http_session:
            await self._http_session.close()

    async def _send_admin_dm(self, message: str):
        try:
            if ADMIN_DISCORD_ID:
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
        if not self._http_session:
            self._http_session = aiohttp.ClientSession()
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
        # Send to all subscriptions
        subs = await self.store.get_subscriptions()
        if not subs:
            logger.info("No subscriptions configured; skipping announcements")
            return

        messages = []
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

            # Check if details are valid/useful
            # Use explicit check for type narrowing
            if details and "Unknown" not in details.get("name", "Unknown"):
                # High-quality scrape: Send Custom Embed
                embed = discord.Embed(
                    title=details["name"],
                    description=parsed.get("text"),
                    color=discord.Color.default(),
                )

                if details.get("image"):
                    embed.set_image(url=details["image"])

                # Store Page
                if details.get("store_url"):
                    embed.add_field(name="Store", value=details["store_url"], inline=False)

                # Helper to normalize for comparison
                def norm(u):
                    return u.rstrip("/") if u else ""

                store_url = details.get("store_url")
                source_set = set(parsed.get("source_links", []))

                # Other valid links (excluding the primary store link and sources)
                other_links = []
                for link in parsed.get("links", []):
                    if store_url and norm(link) == norm(store_url):
                        continue
                    if link in source_set:
                        continue
                    other_links.append(link)

                if other_links:
                    embed.add_field(name="Direct Links", value="\n".join(other_links), inline=False)

                # Source links (e.g. Reddit)
                sources = parsed.get("source_links", [])
                if sources:
                    embed.add_field(name="Sources", value="\n".join(sources), inline=False)

                messages.append((embed, None))  # None for content override (handled in loop)
            else:
                # Scrape failed or low quality: Fallback to plain text so Discord embeds the link
                # Construct a nice text message
                text_content = parsed.get("text", "")

                # Append links if not in text
                all_links = parsed.get("links", []) + parsed.get("source_links", [])
                links_to_add = [link for link in all_links if link not in text_content]

                if links_to_add:
                    text_content += "\n\n" + "\n".join(links_to_add)

                messages.append((None, text_content))

        # iterate subs and send
        # subs is likely list of (guild_id, channel_id, role_id)
        for _guild_id, channel_id, role_id in subs:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                # Try fetching if not in cache
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                except Exception as e:
                    logger.warning(f"Could not fetch channel {channel_id}: {e}")
                    continue

            if not channel:
                continue

            if not isinstance(channel, discord.abc.Messageable):
                logger.warning(f"Channel {channel_id} is not messageable (Type: {type(channel)})")
                continue

            mention = f"<@&{role_id}> " if role_id else ""

            for embed_obj, text_content in messages:
                try:
                    if embed_obj:
                        # Custom Embed path
                        await channel.send(content=mention if mention else None, embed=embed_obj)
                    else:
                        # Fallback text path
                        full_msg = (mention + text_content) if mention else text_content
                        await channel.send(content=full_msg)
                except Exception as e:
                    logger.exception("Failed to send announcement to %s: %s", channel_id, e)

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
            await ctx.send("Unauthorized. Only admin may run this command.")
            return

        await ctx.send(f"Generating test embed for Steam ID: {steam_id}...")
        if not self.steam_manager:
            await ctx.send("Steam manager not initialized.")
            return

        details = await get_game_details(steam_id, self.steam_manager, self.store)

        if not details:
            await ctx.send("Could not fetch details for that Steam ID (it might be invalid or hidden).")
            return

        embed = discord.Embed(
            title=details.get("name", "Unknown Game"),
            description=(
                f"This is a test announcement for **{details.get('name')}**. "
                "This text simulates the post content from Bluesky."
            ),
            color=discord.Color.green() if details.get("is_free") else discord.Color.blue(),
        )

        if details.get("image"):
            embed.set_image(url=details["image"])

        if details.get("store_url"):
            embed.add_field(name="Store Page", value=f"[Link to Steam]({details['store_url']})", inline=False)

        price = details.get("price_info")
        if price:
            if isinstance(price, dict):
                orig = price.get("original_price")
                curr = price.get("current_price")
                perc = price.get("discount_percent")
                price_str = f"~~{orig}~~ **{curr}** (-{perc}%)"
            else:
                price_str = str(price)
            embed.add_field(name="Price", value=price_str, inline=True)

        if details.get("release_date"):
            embed.add_field(name="Release Date", value=details["release_date"], inline=True)

        devs = details.get("developers", [])
        if devs:
            embed.set_footer(text=f"Developed by {', '.join(devs)}")

        await ctx.send(embed=embed)

    @commands.command(name="test_embed_epic")
    async def test_embed_epic_command(self, ctx: commands.Context, slug: str = "p/fortnite"):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return

        await ctx.send(f"Generating test embed for Epic Slug: {slug}...")
        if not self.epic_manager:
            await ctx.send("Epic manager not initialized.")
            return

        details = await get_epic_details(slug, self.epic_manager, self.store)

        if not details:
            await ctx.send("Could not fetch details for that Epic slug.")
            return

        embed = discord.Embed(
            title=details.get("name", "Unknown Game"),
            description=f"This is a test announcement for **{details.get('name')}** on Epic Games Store.",
            color=discord.Color.purple(),  # Epic is often associated with dark/purple or black
        )

        if details.get("image"):
            embed.set_image(url=details["image"])

        # Epic URLs usually follow this pattern, or we can construct it
        store_url = f"https://store.epicgames.com/{slug}"
        embed.add_field(name="Store Page", value=f"[Link to Epic]({store_url})", inline=False)

        price = details.get("price_info")
        embed.add_field(name="Price", value=str(price), inline=True)

        if details.get("release_date"):
            embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

        devs = details.get("developers", [])
        if devs:
            embed.set_footer(text=f"Developed by {', '.join(devs)}")

        await ctx.send(embed=embed)

    @commands.command(name="test_embed_itch")
    async def test_embed_itch_command(self, ctx: commands.Context, url: str):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return

        await ctx.send(f"Generating test embed for Itch URL: {url}...")
        if not self.itch_manager:
            await ctx.send("Itch manager not initialized.")
            return

        details = await get_itch_details(url, self.itch_manager, self.store)

        if not details:
            await ctx.send("Could not fetch details for that Itch URL.")
            return

        embed = discord.Embed(
            title=details.get("name", "Unknown Game"),
            description=f"This is a test announcement for **{details.get('name')}** on itch.io.",
            color=discord.Color.red(),  # Itch red
        )

        if details.get("image"):
            embed.set_image(url=details["image"])

        embed.add_field(name="Store Page", value=f"[Link to Itch]({url})", inline=False)

        price = details.get("price_info")
        embed.add_field(name="Price", value=str(price), inline=True)

        if details.get("release_date"):
            embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

        devs = details.get("developers", [])
        if devs:
            embed.set_footer(text=f"Developed by {', '.join(devs)}")

        await ctx.send(embed=embed)

    @commands.command(name="test_embed_ps")
    async def test_embed_ps_command(self, ctx: commands.Context, url: str):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return

        await ctx.send(f"Generating test embed for PS URL: {url}...")
        if not self.ps_manager:
            await ctx.send("PS manager not initialized.")
            return

        details = await get_ps_details(url, self.ps_manager, self.store)

        if not details:
            await ctx.send("Could not fetch details for that PS URL.")
            return

        embed = discord.Embed(
            title=details.get("name", "Unknown Game"),
            description=f"This is a test announcement for **{details.get('name')}** on PlayStation Store.",
            color=discord.Color.blue(),
        )

        if details.get("image"):
            embed.set_image(url=details["image"])

        embed.add_field(name="Store Page", value=f"[Link to PS Store]({url})", inline=False)

        price = details.get("price_info")
        embed.add_field(name="Price", value=str(price), inline=True)

        if details.get("release_date"):
            embed.add_field(name="Release Date", value=str(details["release_date"]), inline=True)

        devs = details.get("developers", [])
        if devs:
            embed.set_footer(text=f"Developed by {', '.join(devs)}")

        await ctx.send(embed=embed)

    @commands.command(name="test_scraper")
    async def test_scraper_command(self, ctx: commands.Context, limit: int = 5):
        if ADMIN_DISCORD_ID and str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            await ctx.send("Unauthorized. Only admin may run this command.")
            return

        await ctx.send(f"Testing scraper (fetching last {limit} posts)...")
        if not self._http_session:
            self._http_session = aiohttp.ClientSession()

        try:
            fetcher = BlueskyFetcher(self._http_session)
            posts = await fetcher.fetch_latest(limit=limit)

            if not posts:
                await ctx.send("No posts found.")
                return

            await ctx.send(f"Found {len(posts)} posts. Processing...")

            for raw in posts:
                uri = raw.get("uri")
                text = raw.get("record", {}).get("text", "")

                # Logic duplicated from _process_feed but without seen check
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

                    # Generate Embed or Fallback
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

                    if details and "Unknown" not in details.get("name", "Unknown"):
                        embed = discord.Embed(
                            title=details["name"],
                            description=parsed.get("text"),
                            color=discord.Color.default(),
                        )

                        if details.get("image"):
                            embed.set_image(url=details["image"])

                        if details.get("store_url"):
                            embed.add_field(name="Store", value=details["store_url"], inline=False)

                        # Helper to normalize for comparison
                        def norm(u):
                            return u.rstrip("/") if u else ""

                        store_url = details.get("store_url")
                        source_set = set(parsed.get("source_links", []))

                        # Other valid links
                        other_links = []
                        for link in parsed.get("links", []):
                            if store_url and norm(link) == norm(store_url):
                                continue
                            if link in source_set:
                                continue
                            other_links.append(link)

                        if other_links:
                            embed.add_field(name="Direct Links", value="\n".join(other_links), inline=False)

                        # Source links
                        sources = parsed.get("source_links", [])
                        if sources:
                            embed.add_field(name="Sources", value="\n".join(sources), inline=False)

                        await ctx.send(embed=embed)
                    else:
                        # Fallback: Send plain text
                        text_content = parsed.get("text", "")
                        all_links = parsed.get("links", []) + parsed.get("source_links", [])
                        links_to_add = [link for link in all_links if link not in text_content]
                        if links_to_add:
                            text_content += "\n\n" + "\n".join(links_to_add)

                        await ctx.send(content=text_content)
                else:
                    await ctx.send(f"Skipped post (no valid links): {uri}")

            await ctx.send("Scraper test complete.")

        except Exception as e:
            logger.exception("Scraper test failed: %s", e)
            await ctx.send(f"Scraper test failed: {e}")

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
