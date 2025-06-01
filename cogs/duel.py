import discord
from discord.ext import commands
import aiohttp, random, asyncio, json, os
import datetime as dt
from collections import defaultdict
from graphql_queries import QUERY_DUEL_PROBLEM, QUERY_SINGLE_PROBLEM, QUERY_USER_SOLVED

DUEL_TIMEOUT = 30 * 60  # 30 minutes
DUELS = defaultdict(list)
USERNAME_FILE = "usernames.json"

# Load usernames
if os.path.exists(USERNAME_FILE):
    with open(USERNAME_FILE, "r") as f:
        USERNAMES = json.load(f)
else:
    USERNAMES = {}

class Duel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def duel(self, ctx, opponent: discord.Member):
        if ctx.channel.id in DUELS:
            await ctx.send("❌ A duel is already in progress here.")
            return

        challenger_id, opponent_id = str(ctx.author.id), str(opponent.id)

        if challenger_id not in USERNAMES:
            await ctx.send(f"❌ Link your username using `!linkleetcode`.")
            return
        if opponent_id not in USERNAMES:
            await ctx.send(f"❌ {opponent.mention} hasn't linked their username.")
            return

        class DifficultyDropdown(discord.ui.Select):
            def __init__(self, cog):
                options = [discord.SelectOption(label=d, value=d.upper()) for d in ["Easy", "Medium", "Hard"]]
                super().__init__(placeholder="Select difficulty", options=options)
                self.cog = cog

            async def callback(self, interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("Only the challenger can pick.", ephemeral=True)
                    return

                difficulty = self.values[0]
                await interaction.response.send_message(f"Fetching a {difficulty} problem...")
                problem = await self.cog.fetch_random_problem(difficulty)
                if not problem:
                    await ctx.send("Couldn't fetch a problem. Try again later.")
                    return

                slug = problem['titleSlug']
                title = problem['title']
                url = f"https://leetcode.com/problems/{slug}/"
                await ctx.send(f"🤺 **{title}**\n{url}\n30 minutes, GO!")

                duel_data = {
                    "slug": slug,
                    "challenger": ctx.author,
                    "opponent": opponent,
                    "start_time": dt.datetime.now(dt.timezone.utc).timestamp()
                }
                DUELS[ctx.channel.id].append(duel_data)
                self.cog.bot.loop.create_task(self.cog.watch_duel(ctx.channel, duel_data))

        class DuelView(discord.ui.View):
            def __init__(self, cog):
                super().__init__()
                self.add_item(DifficultyDropdown(cog))

        await ctx.send(f"⚔️ {ctx.author.mention} vs {opponent.mention}!", view=DuelView(self))

    async def fetch_random_problem(self, difficulty):
        
        async with aiohttp.ClientSession() as session:
            for _ in range(10):
                vars = {"categorySlug": "", "skip": random.randint(0, 500), "limit": 1, "filters": {"difficulty": difficulty}}
                async with session.post("https://leetcode.com/graphql", json={"query": QUERY_DUEL_PROBLEM, "variables": vars}) as resp:
                    data = await resp.json()
                    questions = data["data"]["problemsetQuestionList"]["questions"]
                    if questions:
                        question = questions[0]
                        slug = question["titleSlug"]
                        async with session.post("https://leetcode.com/graphql", json={"query": QUERY_SINGLE_PROBLEM, "variables": {"titleSlug": slug}}) as sub_resp:
                            sub_data = await sub_resp.json()
                            if not sub_data["data"]["question"]["isPaidOnly"]:
                                return question
        return None

    async def has_solved(self, username, slug, since_timestamp):
        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.com/graphql", json={"query": QUERY_USER_SOLVED, "variables": {"username": username, "limit": 2}}) as resp:
                data = await resp.json()
                for sub in data.get("data", {}).get("recentAcSubmissionList", []):
                    if sub["titleSlug"] == slug and int(sub["timestamp"]) >= since_timestamp:
                        return True
        return False

    async def watch_duel(self, channel, duel):
        slug, challenger, opponent, start = duel.values()
        timeout = start + DUEL_TIMEOUT
        winner = None
        while dt.datetime.now(dt.timezone.utc).timestamp() < timeout:
            for user in [challenger, opponent]:
                uid = str(user.id)
                if uid in USERNAMES and await self.has_solved(USERNAMES[uid], slug, start):
                    winner = user
                    break
            if winner:
                break
            await asyncio.sleep(5)

        result_msg = f"🏆 {winner.mention} wins!" if winner else "⏰ Draw! No solutions submitted."
        await channel.send(result_msg)
        DUELS[channel.id].remove(duel)
        if not DUELS[channel.id]:
            del DUELS[channel.id]

async def setup(bot):
    await bot.add_cog(Duel(bot))
