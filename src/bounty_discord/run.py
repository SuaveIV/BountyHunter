import asyncio

import discord

from bounty_discord.config import BOT_TOKEN
from bounty_discord.gunship import Gunship
from bounty_discord.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


async def main():
    setup_logging()
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return

    intents = discord.Intents.default()
    intents.message_content = True  # Required for commands

    # Initialize the Gunship (Bot)
    bot = Gunship(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        if bot.user:
            logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        # Slash commands removed, no sync needed.
        logger.info("Bot is ready to process prefix commands.")

    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        pass
