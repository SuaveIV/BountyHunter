import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from colorama import Fore, Style
from colorama import init as colorama_init

from .config import ADMIN_DISCORD_ID, BOT_TOKEN, ITAD_API_KEY, LOG_LEVEL


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
        except Exception as e:
            print(f"Error in DiscordLoggingHandler.emit: {e}", file=sys.stderr)  # nosec B110

    async def send_dm(self, message):
        if not ADMIN_DISCORD_ID:
            return
        try:
            user = await self.bot.fetch_user(int(ADMIN_DISCORD_ID))
            if user:
                if len(message) > 1900:
                    message = message[:1900] + "..."
                await user.send(f"🚨 **CRITICAL ERROR** 🚨\n```\n{message}\n```")
        except Exception as e:
            print(f"Error sending DM: {e}", file=sys.stderr)  # nosec B110


class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in logs."""

    def filter(self, record):
        def mask(text):
            if isinstance(text, str):
                if BOT_TOKEN and BOT_TOKEN in text:
                    text = text.replace(BOT_TOKEN, "***BOT_TOKEN***")
                if ITAD_API_KEY and ITAD_API_KEY in text:
                    text = text.replace(ITAD_API_KEY, "***ITAD_API_KEY***")
            return text

        record.msg = mask(record.msg)

        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(mask(arg) for arg in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: mask(v) for k, v in record.args.items()}

        return True


class ConsoleNoiseFilter(logging.Filter):
    """Filter to exclude common noise/safe warnings from the console."""

    def filter(self, record):
        msg = str(record.msg)
        # Filter clock drift from tasks
        if record.name == "discord.ext.tasks" and "Clock drift detected" in msg:
            return False
        # Filter heartbeat blocked warnings (common during heavy processing)
        if record.name == "discord.gateway" and "heartbeat blocked" in msg:
            return False

        # Clean up noisy DNS reconnection logs (keep the message, hide the traceback)
        if record.name == "discord.client" and "Attempting a reconnect" in msg:
            if record.exc_info:
                # Check if it's a DNS/Socket error
                exc_type, _, _ = record.exc_info
                if exc_type and ("ClientConnectorDNSError" in exc_type.__name__ or "gaierror" in exc_type.__name__):
                    # Suppress the traceback for the console
                    record.exc_info = None

        return True


def setup_logging():
    # Force color if requested via environment variable (common in Docker)
    force_color = os.getenv("FORCE_COLOR", "").lower() in ("1", "true")
    colorama_init(autoreset=True, strip=False if force_color else None)

    # Remove existing handlers to ensure our configuration takes precedence
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add sensitive data filter to root logger
    for f in root.filters[:]:
        if isinstance(f, SensitiveDataFilter):
            root.removeFilter(f)
    root.addFilter(SensitiveDataFilter())

    # Set root to DEBUG to capture all logs; handlers will filter as needed
    root.setLevel(logging.DEBUG)

    # Console Handler (Colored) - Uses configured LOG_LEVEL
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(
        logging.Formatter(
            f"{Fore.CYAN}%(asctime)s{Style.RESET_ALL} | "
            f"{Fore.GREEN}%(levelname)s{Style.RESET_ALL}: "
            f"{Fore.YELLOW}%(name)s{Style.RESET_ALL} - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    console_handler.addFilter(ConsoleNoiseFilter())
    root.addHandler(console_handler)

    # File Handler (Plain text, Rotating) - Always DEBUG
    os.makedirs("logs", exist_ok=True)
    file_handler = RotatingFileHandler(
        "logs/bountyhunter.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s: %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    root.addHandler(file_handler)


def get_logger(name: str):
    return logging.getLogger(name)
