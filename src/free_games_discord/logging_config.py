import logging
from .config import LOG_LEVEL

def get_logger(name: str):
    logging.basicConfig(level=LOG_LEVEL)
    return logging.getLogger(name)