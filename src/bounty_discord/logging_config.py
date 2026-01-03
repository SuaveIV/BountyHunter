import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from colorama import Fore, Style
from colorama import init as colorama_init

from .config import BOT_TOKEN, ITAD_API_KEY, LOG_LEVEL


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
        return True


def setup_logging():
    colorama_init(autoreset=True)
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
