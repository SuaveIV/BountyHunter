import logging

import aiohttp
from discord.ext import commands

from bounty_core.epic_api_manager import EpicAPIManager
from bounty_core.fetcher import RedditRSSFetcher
from bounty_core.itad_api_manager import ItadAPIManager
from bounty_core.itch_api_manager import ItchAPIManager
from bounty_core.ps_api_manager import PSAPIManager
from bounty_core.steam_api_manager import SteamAPIManager
from bounty_core.store import Store
from bounty_discord.modules.sector_scanner import SectorScanner

from .config import ADMIN_DISCORD_ID, DATABASE_PATH, ITAD_API_KEY
from .logging_config import DiscordLoggingHandler, get_logger

logger = get_logger(__name__)


class Gunship(commands.Bot):
    """
    The main bot class (Gunship) that manages resources and extensions.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initialize Shared Resources
        self.store = Store(DATABASE_PATH)
        self._http_session = None

        # Managers placeholders (init in setup_hook or async context preferred,
        # but for consistency with original code, we can init them here if session is ready.
        # However, we need an async session. Ideally we create session in setup_hook?
        # The original code created session in __init__ (synchronously).
        # We'll follow the pattern: create session in __init__ (synchronously instantiated object)
        # but it's better practice to do it in setup_hook or start.
        # Let's stick to __init__ for session creation to match original behavior if possible,
        # but aiohttp.ClientSession() is sync constructor.
        self._http_session = aiohttp.ClientSession()

        self.steam_manager = SteamAPIManager(session=self._http_session)
        self.epic_manager = EpicAPIManager(session=self._http_session)
        self.itch_manager = ItchAPIManager(session=self._http_session)
        self.ps_manager = PSAPIManager(session=self._http_session)
        self.itad_manager = ItadAPIManager(session=self._http_session, api_key=ITAD_API_KEY)
        self.scanner = SectorScanner(RedditRSSFetcher(self._http_session), self.store)

        # Logging Handler
        self.discord_log_handler = None

    async def setup_hook(self):
        # Setup Critical Error Logging to DM
        self.discord_log_handler = DiscordLoggingHandler(self)
        self.discord_log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logging.getLogger().addHandler(self.discord_log_handler)

        # Load Cogs (Extensions)
        extensions = [
            "bounty_discord.cogs.visor",
            "bounty_discord.cogs.admin",
            "bounty_discord.cogs.codex",
            "bounty_discord.cogs.beacons",
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.exception(f"Failed to load extension {ext}: {e}")

        if not ADMIN_DISCORD_ID:
            logger.warning("ADMIN_DISCORD_ID is not set. Admin commands and error DMs will be disabled.")

    async def close(self):
        if self.discord_log_handler:
            logging.getLogger().removeHandler(self.discord_log_handler)

        if self._http_session:
            await self._http_session.close()

        await super().close()
