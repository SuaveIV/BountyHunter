import os
from interactions import Client
from bounty_discord.bot import Bounty
from bounty_discord.config import BOT_TOKEN

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")
    client = Client(token=BOT_TOKEN, default_scope=None)
    client.load_extension(Bounty(client))
    client.start()

if __name__ == "__main__":
    main()