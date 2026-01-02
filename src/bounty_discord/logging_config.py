import logging

from colorama import Fore, Style
from colorama import init as colorama_init

from .config import LOG_LEVEL


def setup_logging():
    colorama_init(autoreset=True)
    logging.basicConfig(
        level=logging.INFO,
        format=f"{Fore.CYAN}%(asctime)s{Style.RESET_ALL} | "
        f"{Fore.GREEN}%(levelname)s{Style.RESET_ALL}: "
        f"{Fore.YELLOW}%(name)s{Style.RESET_ALL} - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str):
    logging.basicConfig(level=LOG_LEVEL)
    return logging.getLogger(name)
