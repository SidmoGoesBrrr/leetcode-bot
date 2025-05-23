import discord
from discord import File
from discord.ext import commands, tasks
import aiohttp, random, os, asyncio, json, logging
import datetime as dt
from zoneinfo import ZoneInfo  # Use Python 3.9+ zoneinfo

# ------------------------- Debug Logging to File -------------------------
logger = logging.getLogger("leetcode_bot")
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("leetcode_bot_log.log")
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ------------------------- Intents and Bot Setup -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True  # Required to fetch role members!
bot = commands.Bot(command_prefix="!", intents=intents)

CHALLENGE_CHANNEL_ID = 1348527848843120683
ROLE_ID = 1348563397230202961

# ------------------------- GraphQL Queries -------------------------
query_total = """
query {
  problemsetQuestionList: questionList(
    categorySlug: ""
    limit: 1
    skip: 0
    filters: {difficulty: EASY}
  ) {
    total: totalNum
  }
}
"""

query_problem = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      title
      titleSlug
      difficulty
      topicTags {
        name
      }
    }
  }
}
"""

# GraphQL query for accepted submissions
QUERY_ACCEPTED = """
#graphql
query getACSubmissions ($username: String!, $limit: Int) {
    recentAcSubmissionList(username: $username, limit: $limit) {
        title
        titleSlug
        timestamp
        statusDisplay
        lang
    }
}
"""

# ------------------------- Global Data Files -------------------------
USERS_FILE = "users.json"       # Maps Discord user IDs to their LeetCode username and Discord name.
BALANCES_FILE = "balances.json"   # Maps Discord user IDs to their cumulative balance.

# Load or initialize registered users
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r") as f:
        bot.users_data = json.load(f)
else:
    bot.users_data = {}

# Load or initialize balances
if os.path.exists(BALANCES_FILE):
    with open(BALANCES_FILE, "r") as f:
        bot.balances = json.load(f)
else:
    bot.balances = {}

# ------------------------- Challenge Data -------------------------
# Track two daily challenges

bot.current_challenge_slugs = []     # [slug1, slug2]

bot.challenge_post_times   = []     # [datetime1, datetime2]

bot.status_message         = None   # Combined status message

bot.status_updater         = None   # Task handle for update_status_loop



# Explanation workflow keyed by (user_id, problem_index)

bot.pending_explanations = {}  # {(user_id, idx): discord.Member}

bot.explanations         = {}  # {(user_id, idx): {"type":..., "content"/"file_path":...}}

# ------------------------- Helper Functions -------------------------
async def fetch_problem():
    """Fetch a random unused Easy problem."""
    logger.debug("Starting fetch_problem()")
    try:
        with open("sent_problems.json", "r") as f:
            used_slugs = json.load(f)
    except FileNotFoundError:
        used_slugs = []

    query_single_problem = """
    query questionTitle($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        title
        titleSlug
        difficulty
        isPaidOnly
        topicTags {
          name
        }
      }
    }
    """

    async with aiohttp.ClientSession() as session:
        logger.debug("Fetching total number of problems from LeetCode API")
        async with session.post("https://leetcode.com/graphql", json={"query": query_total}) as resp:
            data = await resp.json()

        if "data" not in data or "problemsetQuestionList" not in data["data"]:
            logger.error("Unexpected response format from LeetCode API: %s", data)
            return None

        total = data["data"]["problemsetQuestionList"]["total"]

        
        for _ in range(10):

            skip = random.randrange(total)

            vars = {"categorySlug": "", "skip": skip, "limit": 1, "filters": {"difficulty": "EASY"}}

            async with session.post("https://leetcode.com/graphql", json={"query": query_problem, "variables": vars}) as resp:
                result = await resp.json()
            qs = result["data"]["problemsetQuestionList"]["questions"]
            if not qs:
                await asyncio.sleep(0.5)
                continue

            qdata = qs[0]
            slug  = qdata["titleSlug"]
            # ensure not premium
            async with session.post("https://leetcode.com/graphql", json={"query": query_single_problem, "variables": {"titleSlug": slug}}) as resp:

                full = await resp.json()

            if full["data"]["question"]["isPaidOnly"]:

                await asyncio.sleep(0.5)
                continue

            if slug not in used_slugs:
                used_slugs.append(slug)
                with open("sent_problems.json", "w") as f:
                    json.dump(used_slugs, f)
                logger.info("Fetched new problem: %s (%s)", qdata["title"], slug)
                return qdata
            else:
                logger.debug("Problem %s already used. Trying again.", slug)
            await asyncio.sleep(0.5)
        return None
    
async def query_user_submissions(leetcode_username: str):
    """Get recent AC submissions for a user."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://leetcode.com/graphql",
                                    json={"query": QUERY_ACCEPTED, "variables": {"username": leetcode_username, "limit": 20}}) as resp:
                if resp.content_type != 'application/json':
                    text = await resp.text()
                    logger.error(f"Non-JSON response for {leetcode_username}: {text[:300]}")
                    return []
                data = await resp.json()
        return data.get("data", {}).get("recentAcSubmissionList", [])
    except Exception as e:
        logger.error(f"Failed to fetch submissions for {leetcode_username}: {e}")
        return []


# ------------------------- Commands -------------------------
@bot.command()
async def register(ctx, leetcode_username: str):
    """Register your LeetCode username for challenge tracking."""
    user_id = str(ctx.author.id)
    bot.users_data[user_id] = {"discord_username": ctx.author.name, "leetcode_username": leetcode_username}
    with open(USERS_FILE, "w") as f:
        json.dump(bot.users_data, f)
    if user_id not in bot.balances:
        bot.balances[user_id] = 0
    logger.info("User %s registered with LeetCode username: %s", ctx.author.name, leetcode_username)
    await ctx.send(f"Registered {ctx.author.name} with LeetCode username: {leetcode_username}")

@bot.command()
async def monthly(ctx):
    """Computes fair cost-sharing settlements between all users."""
    if not bot.balances:
        await ctx.send("No balance data available.")
        return

    user_ids = list(bot.balances.keys())
    n = len(user_ids)
    total = sum(bot.balances.values())
    fair_share = total / n

    net_positions = {}
    for uid in user_ids:
        actual = bot.balances[uid]
        net = round(actual - fair_share, 2)
        net_positions[uid] = net

    creditors = [(uid, amt) for uid, amt in net_positions.items() if amt > 0.01]
    debtors = [(uid, amt) for uid, amt in net_positions.items() if amt < -0.01]

    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1])

    settlements = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debtor_amt = debtors[i]
        creditor_id, creditor_amt = creditors[j]
        pay_amt = min(-debtor_amt, creditor_amt)
        pay_amt = round(pay_amt, 2)
        debtor_name = bot.users_data.get(debtor_id, {}).get("discord_username", "Unknown")
        creditor_name = bot.users_data.get(creditor_id, {}).get("discord_username", "Unknown")
        settlements.append(f"**{debtor_name} pays Rs {pay_amt} to {creditor_name}**")
        debtor_amt += pay_amt
        creditor_amt -= pay_amt
        debtors[i] = (debtor_id, debtor_amt)
        creditors[j] = (creditor_id, creditor_amt)
        if abs(debtor_amt) < 0.01:
            i += 1
        if abs(creditor_amt) < 0.01:
            j += 1

    await ctx.send("📊 **Net Positions (after fair share calculation)**")
    summary = []
    for uid in user_ids:
        name = bot.users_data.get(uid, {}).get("discord_username", "Unknown")
        net = net_positions[uid]
        status = "is owed" if net > 0 else "owes"
        summary.append(f"{name}: {status} Rs {abs(net)}")
    await ctx.send("```" + "\n".join(summary) + "```")

    if settlements:
        await ctx.send("🧾 **Settlement Instructions**")
        for line in settlements:
            await ctx.send(line)
            await asyncio.sleep(1)
    else:
        await ctx.send("✅ Everyone is settled!")

    for uid in user_ids:
        bot.balances[uid] = 0
    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)

@bot.command()
async def leaderboard(ctx):
    """Displays the leaderboard based on cumulative balances."""
    if not bot.balances:
        await ctx.send("No leaderboard data available yet.")
        return
    sorted_balances = sorted(bot.balances.items(), key=lambda x: x[1], reverse=True)
    embed = discord.Embed(title="Leaderboard", color=discord.Color.gold())
    rank = 1
    for user_id, balance in sorted_balances:
        user_info = bot.users_data.get(user_id, {})
        discord_name = user_info.get("discord_username", "Unknown")
        embed.add_field(name=f"{rank}. {discord_name}", value=f"Balance: Rs {balance}", inline=False)
        rank += 1
    await ctx.send(embed=embed)

@bot.command()
async def clear(ctx, amount: int):
    """Deletes a specified number of messages (including the command message)."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id and not ctx.author.guild_permissions.manage_messages:
        await ctx.send(f"❌ {ctx.author.mention}, you too weak. 💪")
        return
    if amount < 1:
        await ctx.send("Please specify a number greater than 0.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🗑️ {ctx.author.mention} deleted {len(deleted)-1} messages!", delete_after=3)



@bot.command()
async def sendtoday(ctx):
    """Manually post today's two challenges (admin only)."""
    special = 815555652780294175
    if ctx.author.id != special:
        return await ctx.send("❌ Not authorized.")
    q1 = await fetch_problem()
    q2 = await fetch_problem()
    if q1 and q2:
        await post_two_challenges([q1, q2])
        await ctx.send("✅ Posted today's two challenges.")
    else:
        await ctx.send("⚠️ Could not fetch two problems.")

@bot.command()
async def set_balance(ctx, target: discord.Member, amount: int):
    """Admin-only command to set a specific balance."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id:
        await ctx.send("❌ You are not authorized to use this command.")
        return

    user_id = str(target.id)
    bot.balances[user_id] = amount
    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)
    await ctx.send(f"✅ Balance for {target.display_name} set to Rs {amount}.")

@bot.command()
async def admin_reset(ctx, target: discord.Member):
    """Admin-only command to reset a user's balance to Rs 0."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id:
        await ctx.send("❌ You are not authorized to use this command.")
        return

    user_id = str(target.id)
    bot.balances[user_id] = 0
    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)
    await ctx.send(f"✅ Balance for {target.display_name} has been reset to Rs 0.")

@bot.command()
async def badexplanation(ctx, target: discord.Member):
    """Admin-only command to mark a user's explanation as bad."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id:
        await ctx.send("❌ You are not authorized to use this command.")
        return

    user_id = str(target.id)
    bot.balances[user_id] = bot.balances.get(user_id, 0) - 100
    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)
    await ctx.send(f"❌ {target.display_name}'s explanation has been marked as bad. Rs 100 has been deducted from their balance.")

@bot.command()
async def add100(ctx):
    """Adds Rs 100 to all registered users' balances."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id:
        await ctx.send("You are not authorized to use this command.")
        return

    for user_id in bot.balances:
        bot.balances[user_id] += 100

    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)

    await ctx.send("Rs 100 has been added to all users' balances.")

@bot.command()
async def remove100(ctx):
    """Adds Rs 100 to all registered users' balances."""
    special_user_id = 815555652780294175
    if ctx.author.id != special_user_id:
        await ctx.send("You are not authorized to use this command.")
        return

    for user_id in bot.balances:
        bot.balances[user_id] -= 100

    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)

    await ctx.send("Rs 100 has been removed from all users' balances.")


# ------------------------- Scheduling Times (using ZoneInfo for IST) -------------------------
IST = ZoneInfo("Asia/Kolkata")
daily_time = dt.time(hour=0, minute=35, tzinfo=IST)         # Daily challenge posting at 00:05 IST,
results_time = dt.time(hour=0, minute=0, tzinfo=IST)        # Results & explanation deadline at 12:00 IST

# ------------------------- Challenge and Results Scheduling -------------------------

async def post_two_challenges(qs):
    """Post two embeds and set up the combined status + updater."""
    channel = bot.get_channel(CHALLENGE_CHANNEL_ID)
    guild   = channel.guild
    role    = guild.get_role(ROLE_ID)
    now     = dt.datetime.now(IST)

    # Reset
    bot.current_challenge_slugs.clear()
    bot.challenge_post_times.clear()
    bot.pending_explanations.clear()
    bot.explanations.clear()
    if bot.status_message:
        try: await bot.status_message.delete()
        except: pass

    # Post each problem
    for i, q in enumerate(qs, start=1):
        title, slug = q["title"], q["titleSlug"]
        diff = q["difficulty"]
        color = discord.Color.green() if diff=="Easy" else discord.Color.yellow()
        url = f"https://leetcode.com/problems/{slug}/"

        embed = discord.Embed(title=f"Problem {i}: {title}", url=url, color=color)
        embed.add_field(name="Difficulty", value=diff, inline=True)
        await channel.send(f"{role.mention} Daily LeetCode Challenge {i}!", embed=embed)

        bot.current_challenge_slugs.append(slug)
        bot.challenge_post_times.append(now)

    # Combined status
    status_text = (
        "Status Update:\n"
        "Problem 1 → Solved: 0 | Pending: (calculating...)\n"
        "Problem 2 → Solved: 0 | Pending: (calculating...)"
    )
    bot.status_message = await channel.send(status_text)

    # Start live updater
    if bot.status_updater:
        bot.status_updater.cancel()
    bot.status_updater = bot.loop.create_task(update_status_loop())

@tasks.loop(time=daily_time)
async def send_daily_challenge():
    q1 = await fetch_problem()
    q2 = await fetch_problem()
    if q1 and q2:
        await post_two_challenges([q1, q2])
    else:
        logger.error("Could not fetch two challenges today.")

async def update_status_loop():
    channel = bot.get_channel(CHALLENGE_CHANNEL_ID)
    guild   = channel.guild
    role    = guild.get_role(ROLE_ID)
    end     = dt.datetime.now(IST).replace(hour=results_time.hour, minute=results_time.minute, second=0)
    if dt.datetime.now(IST) >= end:
        end += dt.timedelta(days=1)

    while dt.datetime.now(IST) < end:
        counts   = [0, 0]
        pendings = [[], []]

        for member in role.members:
            if member.bot:
                continue
            uid = str(member.id)
            if uid not in bot.users_data:
                continue

            subs = await query_user_submissions(bot.users_data[uid]["leetcode_username"])
            await asyncio.sleep(0.3)

            for idx, slug in enumerate(bot.current_challenge_slugs):
                solved = False
                for sub in subs:
                    if sub["titleSlug"] == slug:
                        t = dt.datetime.fromtimestamp(int(sub["timestamp"]), tz=ZoneInfo("UTC")).astimezone(IST)
                        if t >= bot.challenge_post_times[idx]:
                            solved = True
                            break

                if solved:
                    counts[idx] += 1
                    key = (uid, idx)
                    if key not in bot.pending_explanations and key not in bot.explanations:
                        bot.pending_explanations[key] = member
                        await member.send(
                            f"🎉 Congrats on solving today’s problem {idx+1} (`{slug}`)! "
                            "Please reply with a 20–500 character explanation (or attach an image)."
                        )
                else:
                    pendings[idx].append(member.display_name)

                await asyncio.sleep(0.2)

        status_text = (
            f"Status Update:\n"
            f"Problem 1 → Solved: {counts[0]} | Pending: {', '.join(pendings[0]) or 'None'}\n"
            f"Problem 2 → Solved: {counts[1]} | Pending: {', '.join(pendings[1]) or 'None'}"
        )
        try:
            await bot.status_message.edit(content=status_text)
        except Exception as e:
            logger.error("Failed to update status: %s", e)

        await asyncio.sleep(300)

    await bot.status_message.edit(content="Submission window closed.")

@tasks.loop(time=results_time)
async def compile_and_post_results():
    channel = bot.get_channel(CHALLENGE_CHANNEL_ID)
    guild   = channel.guild
    role    = guild.get_role(ROLE_ID)

    solved_lists   = [[], []]
    unsolved_lists = [[], []]

    for member in role.members:
        if member.bot:
            continue
        uid = str(member.id)
        if uid not in bot.users_data:
            continue

        subs = await query_user_submissions(bot.users_data[uid]["leetcode_username"])
        for idx, slug in enumerate(bot.current_challenge_slugs):
            done = any(
                sub["titleSlug"] == slug and
                dt.datetime.fromtimestamp(int(sub["timestamp"]), tz=ZoneInfo("UTC")).astimezone(IST) >= bot.challenge_post_times[idx]
                for sub in subs
            )
            key = (uid, idx)
            if done and key in bot.explanations:
                solved_lists[idx].append(member.display_name)
            else:
                unsolved_lists[idx].append(member.display_name)
                bot.balances[uid] = bot.balances.get(uid, 0) - 100

    desc = ""
    for idx in (0, 1):
        desc += f"**Problem {idx+1} Solved**\n{', '.join(solved_lists[idx]) or 'None'}\n\n"
        desc += f"**Problem {idx+1} Did Not Solve**\n{', '.join(unsolved_lists[idx]) or 'None'}\n\n"

    desc += "**Monthly Balances**\n"
    for uid, bal in sorted(bot.balances.items(), key=lambda x: bot.users_data[x[0]]["discord_username"].lower()):
        desc += f"{bot.users_data[uid]['discord_username']}: Rs {bal}\n"

    embed = discord.Embed(title="Today's Challenge Results", description=desc, color=discord.Color.blue())
    await channel.send(embed=embed)

    # Persist balances
    with open(BALANCES_FILE, "w") as f:
        json.dump(bot.balances, f)


# ------------------------- DM Handling for Explanation Submissions -------------------------
@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.guild:
        return
    uid = str(message.author.id)
    for key in list(bot.pending_explanations):
        user_id, idx = key
        if user_id != uid:
            continue
        # length checks
        if message.content and len(message.content) > 500:
            return await message.channel.send("Your explanation is too long (>500 chars).")
        if message.content and len(message.content) < 20:
            return await message.channel.send("Your explanation is too short (<20 chars).")

        exp = {}
        if message.content:
            exp["type"] = "text"
            exp["content"] = message.content
        elif message.attachments:
            att = message.attachments[0]
            os.makedirs("explanations", exist_ok=True)
            path = f"explanations/{bot.current_challenge_slugs[idx]}_{uid}_{att.filename}"
            await att.save(path)
            exp["type"] = "attachment"
            exp["file_path"] = path
        else:
            return await message.channel.send("Please provide text or attach an image.")

        bot.explanations[key] = exp
        del bot.pending_explanations[key]
        return await message.channel.send("✅ Explanation recorded!")

# ------------------------- Bot Startup -------------------------
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="a code race!"))
    logger.info("Logged in as %s", bot.user)
    if not send_daily_challenge.is_running():
        send_daily_challenge.start()
    if not compile_and_post_results.is_running():
        compile_and_post_results.start()

# ------------------------- Start the Bot -------------------------
TOKEN = os.getenv("DISCORD_TOKEN")  
bot.run(TOKEN)
