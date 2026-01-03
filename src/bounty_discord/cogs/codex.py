import discord
from discord.ext import commands

from ..config import ITAD_API_KEY
from ..logging_config import get_logger

logger = get_logger(__name__)


class GalacticCodex(commands.Cog):
    """
    Galactic Codex: Information retrieval and price checks.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="price")
    async def check_price(self, ctx: commands.Context, *, title: str):
        """Check price of a game using IsThereAnyDeal."""
        await ctx.send(f"🔍 Checking price for `{title}`...")

        if not ITAD_API_KEY:
            await ctx.send("❌ ITAD API Key is not configured.")
            return

        # Access itad_manager from bot
        if not self.bot.itad_manager:
            await ctx.send("❌ ITAD Manager not initialized.")
            return

        try:
            # 1. Search for games
            games = await self.bot.itad_manager.search_game(title, limit=5)
            if not games:
                await ctx.send(f"❌ Game `{title}` not found on IsThereAnyDeal.")
                return

            # 2. Pick best match
            target_title = title.lower()
            best_match = None

            # Exact match check
            for g in games:
                if g["title"].lower() == target_title:
                    best_match = g
                    break

            # Fallback to first result
            if not best_match:
                best_match = games[0]
                # Inform user if name differs significantly (simple check)
                if best_match["title"].lower() != target_title:
                    await ctx.send(f"⚠️ Exact match not found. Showing results for: **{best_match['title']}**")

            game = best_match
            game_id = game["id"]

            # 3. Get Price Overview
            overview = await self.bot.itad_manager.get_game_overview([game_id])
            if not overview or "prices" not in overview or not overview["prices"]:
                await ctx.send(f"❌ No price information available for **{game['title']}**.")
                return

            price_info = next((p for p in overview["prices"] if p["id"] == game_id), None)

            if not price_info:
                await ctx.send(f"❌ No price details found for **{game['title']}**.")
                return

            # 4. Create Embed
            current = price_info.get("current")
            lowest = price_info.get("lowest")

            embed = discord.Embed(title=game.get("title", title), url=price_info["urls"]["game"])
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

        except Exception as e:
            logger.exception(f"Error checking price for {title}: {e}")
            await ctx.send(f"❌ Error checking price: {e}")


async def setup(bot):
    await bot.add_cog(GalacticCodex(bot))
