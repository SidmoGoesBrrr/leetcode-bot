import discord, aiohttp, json, os
from discord.ext import commands
from database import link_leetcode_user, get_user

class Account(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def linkleetcode(self, ctx, username):
        # LeetCode GraphQL endpoint to check if the username exists
        query = """
        query userPublicProfile($username: String!) {
        matchedUser(username: $username) {
            username
        }
        }
        """
        variables = {"username": username}

        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.com/graphql", json={"query": query, "variables": variables}) as resp:
                data = await resp.json()
                user = data.get("data", {}).get("matchedUser", None)
                if not user:
                    await ctx.send("❌ Username doesn't exist on LeetCode.")
                    return

        discord_id = str(ctx.author.id)
        await ctx.send(f"✅ Linked to {username}!")
        private_channel = await ctx.guild.create_text_channel(f"{ctx.author.display_name}-progress", category=discord.utils.get(ctx.guild.categories, name="Everything YeetCode"))
        await private_channel.set_permissions(ctx.author, read_messages=True, send_messages=True)
        await private_channel.set_permissions(ctx.guild.default_role, read_messages=False)
        await private_channel.set_permissions(discord.utils.get(ctx.guild.roles, id=1369505327388823562), read_messages=False)

        link_leetcode_user(discord_id, username, private_channel.id)        
        
        await private_channel.send(f"Welcome {ctx.author.mention}! This is your private channel. All your progress will be automatically tracked here.")

async def setup(bot):
    await bot.add_cog(Account(bot))
