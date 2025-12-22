import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/bountyhunter.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))  # minutes
ADMIN_DISCORD_ID = os.getenv("ADMIN_DISCORD_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")