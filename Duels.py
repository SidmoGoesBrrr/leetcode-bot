import discord
from discord.ext import commands
import aiohttp, random, os, asyncio, json
import datetime as dt
from zoneinfo import ZoneInfo
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

DUEL_TIMEOUT = 30 * 60  # 30 minutes
DUELS = defaultdict(list)  # {channel_id: duel_data}
USERNAME_FILE = "usernames.json"

# Load or initialize usernames
if os.path.exists(USERNAME_FILE):
    with open(USERNAME_FILE, "r") as f:
        USERNAMES = json.load(f)
else:
    USERNAMES = {}

query_problem = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    questions: data {
      title
      titleSlug
      difficulty
    }
  }
}
"""
QUERY_SINGLE_PROBLEM = """
query questionTitle($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    isPaidOnly
  }
}
"""

QUERY_ACCEPTED = """
query getACSubmissions ($username: String!, $limit: Int) {
    recentAcSubmissionList(username: $username, limit: $limit) {
        titleSlug
        timestamp
    }
}
"""


async def fetch_random_problem(difficulty):
    async with aiohttp.ClientSession() as session:
        for _ in range(10):
            vars = {"categorySlug": "", "skip": random.randint(0, 500), "limit": 1, "filters": {"difficulty": difficulty}}
            async with session.post("https://leetcode.com/graphql", json={"query": query_problem, "variables": vars}) as resp:
                data = await resp.json()
                questions = data["data"]["problemsetQuestionList"]["questions"]
                if not questions:
                    continue
                question = questions[0]
                slug = question["titleSlug"]
                async with session.post("https://leetcode.com/graphql", json={"query": QUERY_SINGLE_PROBLEM, "variables": {"titleSlug": slug}}) as sub_resp:
                    sub_data = await sub_resp.json()
                    if sub_data["data"]["question"]["isPaidOnly"]:
                        continue
                return question
    return None


async def has_solved(username, slug, since_timestamp):
    async with aiohttp.ClientSession() as session:
        async with session.post("https://leetcode.com/graphql", json={"query": QUERY_ACCEPTED, "variables": {"username": username, "limit": 2}}) as resp:
            data = await resp.json()
            subs = data.get("data", {}).get("recentAcSubmissionList", [])
            for sub in subs:
                if sub["titleSlug"] == slug and int(sub["timestamp"]) >= since_timestamp:
                    return True
    return False

@bot.command()
async def duel(ctx, opponent: discord.Member):
    if ctx.channel.id in DUELS:
        await ctx.send("❌ A duel is already in progress in this channel.")
        return

    challenger_id = str(ctx.author.id)
    opponent_id = str(opponent.id)

    if challenger_id not in USERNAMES:
        await ctx.send(f"❌ You ({ctx.author.mention}) have not linked your LeetCode username using `!linkleetcode`.")
        return
    if opponent_id not in USERNAMES:
        await ctx.send(f"❌ {opponent.mention} has not linked their LeetCode username using `!linkleetcode`.")
        return

    class DifficultyDropdown(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label="Easy", value="EASY"),
                discord.SelectOption(label="Medium", value="MEDIUM"),
                discord.SelectOption(label="Hard", value="HARD")
            ]
            super().__init__(placeholder="Choose difficulty", min_values=1, max_values=1, options=options)

        async def callback(self, interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Only the challenger can choose the difficulty.", ephemeral=True)
                return
            difficulty = self.values[0]
            await interaction.response.send_message(f"🔍 Fetching a {difficulty} problem for the duel...")
            problem = await fetch_random_problem(difficulty)
            if not problem:
                await ctx.send("❌ Couldn't fetch a problem. Try again.")
                return
            slug = problem['titleSlug']
            title = problem['title']
            url = f"https://leetcode.com/problems/{slug}/"
            await ctx.send(f"""🤺 **Duel Started!** First to solve:
**{title}**
<{url}>\n
You have 30 minutes. I'll be watching 👀""")
            duel_data = {
                "slug":        slug,
                "challenger":  ctx.author,
                "opponent":    opponent,
                "start_time":  dt.datetime.now(dt.timezone.utc).timestamp()
            }
            # append to list for this channel
            DUELS[ctx.channel.id].append(duel_data)
            # pass duel_data into watcher
            bot.loop.create_task(watch_duel(ctx.channel, duel_data))


    class DuelView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(DifficultyDropdown())

    await ctx.send(f"⚔️ {ctx.author.mention} has challenged {opponent.mention} to a LeetCode duel!", view=DuelView())

async def watch_duel(channel):
    duel = DUELS[channel.id]
    slug = duel["slug"]
    challenger = duel["challenger"]
    opponent = duel["opponent"]
    start_time = duel["start_time"]
    timeout = start_time + DUEL_TIMEOUT

    solved = None

    while dt.datetime.now(dt.timezone.utc).timestamp() < timeout:
        for user in [challenger, opponent]:
            uid = str(user.id)
            if uid not in USERNAMES:
                continue
            leetcode_username = USERNAMES[uid]
            if await has_solved(leetcode_username, slug, start_time):
                solved = user
                break
        if solved:
            break
        await asyncio.sleep(1)

    if solved:
        await channel.send(f"🏆 {solved.mention} solved the problem first! GG!")
    else:
        await channel.send("⏰ Time's up! No one solved the problem. It's a draw!")
    DUELS[channel.id].remove(duel)
    if not DUELS[channel.id]:
        del DUELS[channel.id]

@bot.command()
async def linkleetcode(ctx, username):
    USERNAMES[str(ctx.author.id)] = username
    with open(USERNAME_FILE, "w") as f:
        json.dump(USERNAMES, f)
    await ctx.send(f"✅ Linked your LeetCode username: {username}")

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game("LeetCode Duels"))
    print(f"Duel bot is online as {bot.user}")

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
