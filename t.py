import os

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set in environment variables.")

print("DISCORD_BOT_TOKEN is set.", DISCORD_TOKEN) 