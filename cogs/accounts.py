import discord, aiohttp, json, os
from discord.ext import commands
from database import link_leetcode_user, get_user
from graphql_queries import QUERY_IF_USER_EXISTS
class Account(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def linkleetcode(self, ctx, username):
        # LeetCode GraphQL endpoint to check if the username exists
        
        variables = {"username": username}

        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.com/graphql", json={"query": QUERY_IF_USER_EXISTS, "variables": variables}) as resp:
                data = await resp.json()
                user = data.get("data", {}).get("matchedUser", None)
                if not user:
                    await ctx.send("❌ Username doesn't exist on LeetCode.")
                    return

        discord_id = str(ctx.author.id)
        await ctx.send(f"✅ Linked to {username}!")
        

        link_leetcode_user(discord_id, username)        
        

async def setup(bot):
    await bot.add_cog(Account(bot))
