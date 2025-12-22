import os
from interactions import Client
from free_games_discord.bot import FreeGames
from free_games_discord.config import BOT_TOKEN

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")
    client = Client(token=BOT_TOKEN, default_scope=None)
    client.load_extension(FreeGames(client))
    client.start()

if __name__ == "__main__":
    main()