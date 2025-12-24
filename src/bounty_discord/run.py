import asyncio

import discord
from discord.ext import commands

from bounty_discord.bot import FreeGames
from bounty_discord.config import BOT_TOKEN
from bounty_discord.logging_config import get_logger

logger = get_logger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return

    intents = discord.Intents.default()
    intents.message_content = True  # Required for commands

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        if bot.user:
            logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        # Slash commands removed, no sync needed.
        logger.info("Bot is ready to process prefix commands.")

    async with bot:
        await bot.add_cog(FreeGames(bot))
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        pass
