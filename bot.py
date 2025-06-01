import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("LeetCode Duels"))
    print(f"Logged in as {bot.user}!")

@bot.command()
async def reload(ctx):
    """Reload all cogs."""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                await bot.reload_extension(f"cogs.{filename[:-3]}")
            except Exception as e:
                await ctx.send(f"❌ Failed to reload {filename[:-3]}: {e}")
                print(f"Failed to reload {filename[:-3]}: {e}")
                return
    await ctx.send("✅ All cogs reloaded successfully.")

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            print(f"Loading cog: {filename[:-3]}")
            await bot.load_extension(f"cogs.{filename[:-3]}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(load_cogs())
    print("Cogs loaded successfully.")
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
