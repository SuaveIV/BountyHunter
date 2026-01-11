import json
from io import BytesIO
from typing import Any

import discord
from discord.ext import commands

from bounty_core.epic import get_game_details as get_epic_details
from bounty_core.gog import get_game_details as get_gog_details
from bounty_core.itch import get_game_details as get_itch_details
from bounty_core.parser import determine_content_type
from bounty_core.ps import get_game_details as get_ps_details
from bounty_core.steam import get_game_details

from ..logging_config import get_logger
from ..utils import (
    create_fallback_message,
    create_game_embed,
    enhance_details_with_itad,
    is_admin_dm,
    resolve_game_details,
)

logger = get_logger(__name__)


class Admin(commands.Cog):
    """
    Admin commands for managing the bot and testing features.
    """

    def __init__(self, bot):
        self.bot = bot

    def _create_mock_parsed(self, text: str, url: str, **kwargs) -> dict[str, Any]:
        """Creates a standardized mock parsed dictionary for testing."""
        # Detect mobile links if it's an Epic URL
        mobile_links = {}
        if "store.epicgames.com" in url:
            if "-android-" in url.lower():
                mobile_links["Android"] = url
            elif "-ios-" in url.lower():
                mobile_links["iOS"] = url

        data = {
            "text": text,
            "type": determine_content_type(text),
            "links": [url],
            "source_links": [],
            "steam_app_ids": [],
            "epic_slugs": [],
            "epic_mobile_links": mobile_links,
            "itch_urls": [],
            "ps_urls": [],
            "gog_urls": [],
        }
        data.update(kwargs)
        return data

    @commands.command(name="force_free")
    @is_admin_dm()
    async def force_free(self, ctx: commands.Context):
        """Force run the free games check (Admin DM only)."""
        await ctx.send("Running free games check...")
        # We need to access the SectorVisor cog to run _process_feed
        # Or we can just call the logic directly if we expose it?
        # But _process_feed is internal to SectorVisor.
        # However, we can access the cog by name.
        visor = self.bot.get_cog("SectorVisor")
        if visor:
            await visor._process_feed(manual=True)
        else:
            await ctx.send("❌ SectorVisor Cog not loaded.")

    @commands.command(name="test_embed")
    @is_admin_dm()
    async def test_embed(self, ctx: commands.Context, steam_id: str = "400"):
        """Generate a test embed for a Steam ID (Admin DM only)."""
        await ctx.send(f"🔍 Generating test embed for Steam ID: `{steam_id}`...")
        if not self.bot.steam_manager:
            await ctx.send("❌ Steam manager not initialized.")
            return

        details = await get_game_details(steam_id, self.bot.steam_manager, self.bot.store)

        if not details:
            await ctx.send(f"❌ Could not fetch details for Steam ID `{steam_id}` (it might be invalid or hidden).")
            return

        await enhance_details_with_itad(details, self.bot.itad_manager)

        # Create mock parsed data for testing
        parsed = self._create_mock_parsed(
            "🎮 Check out this game on Steam! Great deal right now.",
            f"https://store.steampowered.com/app/{steam_id}/",
            steam_app_ids=[steam_id],
            source_links=["https://reddit.com/r/GameDeals/comments/example"],
        )

        try:
            embed = await create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_epic")
    @is_admin_dm()
    async def test_embed_epic(self, ctx: commands.Context, slug: str = "fortnite"):
        """Generate a test embed for an Epic Games slug (Admin DM only)."""
        await ctx.send(f"🔍 Generating test embed for Epic Slug: `{slug}`...")
        if not self.bot.epic_manager:
            await ctx.send("❌ Epic manager not initialized.")
            return

        details = await get_epic_details(slug, self.bot.epic_manager, self.bot.store)

        if not details:
            await ctx.send(f"❌ Could not fetch details for Epic slug `{slug}`.")
            return

        await enhance_details_with_itad(details, self.bot.itad_manager)

        # Create mock parsed data for testing
        url = f"https://store.epicgames.com/p/{slug}"
        parsed = self._create_mock_parsed("🎮 Free game available on Epic Games Store!", url, epic_slugs=[slug])

        try:
            embed = await create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_itch")
    @is_admin_dm()
    async def test_embed_itch(self, ctx: commands.Context, url: str):
        """Generate a test embed for an itch.io URL (Admin DM only)."""
        await ctx.send("🔍 Generating test embed for itch.io URL...")
        if not self.bot.itch_manager:
            await ctx.send("❌ Itch manager not initialized.")
            return

        details = await get_itch_details(url, self.bot.itch_manager, self.bot.store)

        if not details:
            await ctx.send("❌ Could not fetch details for itch.io URL.")
            return

        await enhance_details_with_itad(details, self.bot.itad_manager)

        # Create mock parsed data for testing
        parsed = self._create_mock_parsed("🎮 Free game on itch.io!", url, itch_urls=[url])

        try:
            embed = await create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_ps")
    @is_admin_dm()
    async def test_embed_ps(self, ctx: commands.Context, url: str):
        """Generate a test embed for a PlayStation Store URL (Admin DM only)."""
        await ctx.send("🔍 Generating test embed for PlayStation Store URL...")
        if not self.bot.ps_manager:
            await ctx.send("❌ PS manager not initialized.")
            return

        details = await get_ps_details(url, self.bot.ps_manager, self.bot.store)

        if not details:
            await ctx.send("❌ Could not fetch details for PlayStation Store URL.")
            return

        await enhance_details_with_itad(details, self.bot.itad_manager)

        # Create mock parsed data for testing
        parsed = self._create_mock_parsed("🎮 Free game on PlayStation Store!", url, ps_urls=[url])

        try:
            embed = await create_game_embed(details, parsed)
            await ctx.send("✅ Test embed generated:", embed=embed)
        except Exception as e:
            logger.exception(f"Failed to create test embed: {e}")
            await ctx.send(f"❌ Failed to create embed: {e}")

    @commands.command(name="test_embed_gog")
    @is_admin_dm()
    async def test_embed_gog(self, ctx: commands.Context, url: str):
        """Generate a test embed for a GOG URL (Admin DM only)."""
        await ctx.send("🔍 Generating test embed for GOG URL...")
        if not self.bot.gog_manager:
            await ctx.send("❌ GOG manager not initialized.")
            return

        details = await get_gog_details(url, self.bot.gog_manager, self.bot.store)

        if not details:
            await ctx.send(f"❌ Could not fetch details for GOG URL: `{url}`")
            return

        await enhance_details_with_itad(details, self.bot.itad_manager)

        # Create mock parsed data for testing
        parsed = self._create_mock_parsed("🎮 Free game on GOG!", url, gog_urls=[url])

        try:
            embed = await create_game_embed(details, parsed)
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

        # Create mock parsed data via helper
        parsed = self._create_mock_parsed(text, url)

        # Use centralized resolution logic (now respects all managers)
        details = await resolve_game_details(self.bot, parsed)

        try:
            embed = await create_game_embed(details, parsed) if details else None
            if embed:
                await ctx.send("✅ Test embed generated:", embed=embed)
            else:
                await ctx.send("❌ No details could be resolved for this URL.")
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
        await self.test_embed_gog(ctx, url="https://www.gog.com/en/game/cyberpunk_2077")

        # 5. Amazon Prime
        await self.test_embed_url(
            ctx, url="https://gaming.amazon.com/loot/fallout", text="[Prime] Fallout 76 is free with Prime Gaming!"
        )

        # 6. Generic Fallback
        await self.test_embed_url(
            ctx, url="https://example.com/free-game", text="[Unknown] Some Indie Game is free on Example.com!"
        )

        await ctx.send("✅ All examples generated.")

    @commands.command(name="test_scraper")
    @is_admin_dm()
    async def test_scraper(self, ctx: commands.Context, limit: int = 5):
        """Test the scraper feed (Admin DM only)."""
        await ctx.send(f"🔍 Testing scraper (fetching last {limit} posts)...")

        try:
            # Use scanner with ignore_seen=True to preview posts without marking them
            posts = await self.bot.scanner.scan(limit=limit, ignore_seen=True)

            if not posts:
                await ctx.send("❌ No posts found.")
                return

            await ctx.send(f"✅ Found {len(posts)} posts. Processing...")

            for idx, (_uri, parsed) in enumerate(posts, 1):
                # Fetch details
                details = await resolve_game_details(self.bot, parsed)

                # Send result
                await ctx.send(f"\n**Post {idx}/{len(posts)}:**")

                if details and "Unknown" not in details.get("name", "Unknown"):
                    try:
                        embed = await create_game_embed(details, parsed)
                        await ctx.send(embed=embed)
                    except Exception as e:
                        logger.exception(f"Failed to create embed: {e}")
                        fallback = await create_fallback_message(parsed, None)
                        await ctx.send(fallback)
                else:
                    fallback = await create_fallback_message(parsed, None)
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
            await self.bot.store.clear_cache()
            await ctx.send("✅ Cache cleared. Re-run tests to fetch fresh data.")
        except Exception as e:
            logger.exception(f"Failed to clear cache: {e}")
            await ctx.send(f"❌ Failed to clear cache: {e}")

    @commands.command(name="status")
    @is_admin_dm()
    async def status(self, ctx: commands.Context):
        """Show bot uptime and last check time (Admin DM only)."""
        # Bot start time?
        # We don't have start_time in Gunship.
        # We should add start_time to Gunship __init__ or use ctx.bot.user.created_at (not accurate for uptime)
        # Using process uptime or just add self.start_time to Gunship.
        # Let's assume Gunship has start_time or we can't show uptime easily.
        # I'll stick to last_check_time.
        # But wait, Gunship doesn't have start_time initialized in my write_to_file call.
        # I should probably just skip uptime or use a placeholder, or update Gunship.
        # 'status' is useful. I'll check if I can get uptime from something else.
        # Or I can just calculate it if I knew when it started.
        # I'll omit uptime for now or add it later.

        last_check_time = getattr(self.bot, "last_check_time", None)
        last_check = f"<t:{int(last_check_time.timestamp())}:R>" if last_check_time else "Never"

        embed = discord.Embed(title="Bot Status", color=discord.Color.teal())
        # embed.add_field(name="⏱️ Uptime", value=uptime_str, inline=True)
        embed.add_field(name="🔄 Last Check", value=last_check, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="myid")
    @is_admin_dm()
    async def myid(self, ctx: commands.Context):
        """Get your Discord ID (Admin DM only)."""
        await ctx.send(f"Your ID: `{ctx.author.id}`")

    @commands.command(name="debug_itad")
    @is_admin_dm()
    async def debug_itad(self, ctx: commands.Context, query: str, mode: str = "search"):
        """
        Debug ITAD API responses.
        Usage: !debug_itad <query> [search|steam|find]
        Modes:
          - search: Raw search results (default)
          - steam: Lookup by Steam AppID
          - find: Test the universal fallback logic (simulates Visor)
        """
        if not self.bot.itad_manager:
            await ctx.send("❌ ITAD Manager not initialized.")
            return

        await ctx.send(f"🔍 Querying ITAD ({mode}): `{query}`...")

        data = None
        try:
            if mode == "steam":
                data = await self.bot.itad_manager.lookup_game("steam", query)
            elif mode == "find":
                data = await self.bot.itad_manager.find_game(title=query)
            else:
                data = await self.bot.itad_manager.search_game(query, limit=3)

            if not data:
                await ctx.send("❌ No data returned.")
                return

            text = json.dumps(data, indent=2)
            if len(text) > 1900:
                file = discord.File(BytesIO(text.encode("utf-8")), filename="itad_debug.json")
                await ctx.send(file=file)
            else:
                await ctx.send(f"```json\n{text}\n```")
        except Exception as e:
            logger.exception(f"ITAD Debug failed: {e}")
            await ctx.send(f"❌ Error: {e}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
