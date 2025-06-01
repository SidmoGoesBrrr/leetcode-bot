# cogs/progress.py

import discord
from discord.ext import commands
import aiohttp
import json
from datetime import datetime, timezone
from database import get_user
from graphql_queries import LEETCODE_STATS_QUERY

class ProgressTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_leetcode_stats(self, session: aiohttp.ClientSession, username: str) -> dict | None:
        """
        Fetches one “full stats” payload from LeetCode GraphQL, then
        parses it into a more convenient Python dict:
         - solved counts by difficulty (Easy/Medium/Hard)
         - beat‐percentiles by difficulty (Easy/Medium/Hard)
         - calendar map (midnight‐UTC → #solved) as dict[int,int]
         - streak (int)
        """
        year = datetime.utcnow().year
        payload = {
            "query": LEETCODE_STATS_QUERY,
            "variables": {
                "username": username,
                "year": year,
                "recentN": 1000
            }
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/json"
        }

        async with session.post("https://leetcode.com/graphql", json=payload, headers=headers) as resp:
            if resp.status != 200:
                return None
            result = await resp.json()
            data = result.get("data", {})
            if not data or not data.get("matchedUser"):
                return None

        mu = data["matchedUser"]
        # 1) Difficulty breakdown (Easy/Medium/Hard only):
        raw_counts = mu["submitStatsGlobal"]["acSubmissionNum"]
        counts_by_diff: dict[str, int] = {
            entry["difficulty"]: entry["count"]
            for entry in raw_counts
            if entry["difficulty"] in ("Easy", "Medium", "Hard")
        }

        # 2) Beat‐percentiles (Easy/Medium/Hard only):
        raw_beats = mu.get("problemsSolvedBeatsStats", [])
        beats_by_diff: dict[str, float] = {
            entry["difficulty"]: entry["percentage"]
            for entry in raw_beats
            if entry["difficulty"] in ("Easy", "Medium", "Hard")
        }

        # 3) Calendar + streak:
        cal_str = mu["userCalendar"]["submissionCalendar"]
        try:
            cal_map: dict[str, int] = json.loads(cal_str)
        except json.JSONDecodeError:
            cal_map = {}
        cal_map = {int(k): v for k, v in cal_map.items()}
        streak = mu["userCalendar"]["streak"]

        return {
            "counts_by_diff": counts_by_diff,
            "beats_by_diff": beats_by_diff,
            "calendar": cal_map,
            "streak": streak
        }

    def _compute_time_buckets(self, cal_map: dict[int, int]) -> dict[str, int]:
        """
        Given a calendar map: { UNIX-midnight-UTC : solves_on_that_day },
        return a dict with keys "today", "week", "month" and their counts.
        """
        now = datetime.now(timezone.utc)
        midnight_today = int(datetime(
            year=now.year, month=now.month, day=now.day,
            tzinfo=timezone.utc
        ).timestamp())

        today_count = cal_map.get(midnight_today, 0)

        week_count = 0
        for i in range(7):
            day_mid = midnight_today - (i * 86400)
            week_count += cal_map.get(day_mid, 0)

        month_count = 0
        for i in range(30):
            day_mid = midnight_today - (i * 86400)
            month_count += cal_map.get(day_mid, 0)

        return {
            "today": today_count,
            "week": week_count,
            "month": month_count
        }

    @commands.command(name="stats")
    async def stats(self, ctx, member: discord.Member = None):
        """
        Usage: !stats @User
        If no user is mentioned, defaults to ctx.author.
        Fetches LeetCode stats and builds a streamlined embed without “All” difficulty
        and without the latest‐5 list. Tabs separate Easy/Medium/Hard values.
        """
        if member is None:
            member = ctx.author

        entry = get_user(str(member.id))
        if not entry or not entry.get("leetcode_username"):
            await ctx.send(f"❌ `{member.display_name}` hasn’t linked a LeetCode username yet. Use `!linkleetcode` first.")
            return

        leetcode_name = entry["leetcode_username"]

        async with aiohttp.ClientSession() as session:
            stats = await self.fetch_leetcode_stats(session, leetcode_name)
            if stats is None:
                await ctx.send(f"⚠️ Couldn’t fetch LeetCode stats for `{leetcode_name}`. Are you sure the username is correct?")
                return

        counts = stats["counts_by_diff"]
        beats = stats["beats_by_diff"]
        cal_map = stats["calendar"]
        streak = stats["streak"]

        time_buckets = self._compute_time_buckets(cal_map)

        embed = discord.Embed(
            title=f"📈 LeetCode Stats for {member.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url="https://leetcode.com/static/images/LeetCode_logo_rvs.png")
        embed.set_footer(text="Keep grinding LeetCode! 🚀")

        embed.description = f"**LeetCode Username:** [`{leetcode_name}`](https://leetcode.com/{leetcode_name}/)"

        # Total solved = Easy + Medium + Hard
        easy_ct = counts.get("Easy", 0)
        med_ct = counts.get("Medium", 0)
        hard_ct = counts.get("Hard", 0)
        total_solved = easy_ct + med_ct + hard_ct

        embed.add_field(
            name="🧮 Lifetime Solved",
            value=f"**Total:** `{total_solved}`",
            inline=False
        )

        # Tabs between numbers after emojis:
        embed.add_field(name="🟢 Easy",   value=f"{easy_ct}`",   inline=True)
        embed.add_field(name="🟡 Medium", value=f"`{med_ct}`",   inline=True)
        embed.add_field(name="🔴 Hard",   value=f"`{hard_ct}`",   inline=True)


        # Beat‐percentiles (Easy/Medium/Hard only)
        if beats:
            easy_beat = beats.get("Easy", 0.0)
            med_beat = beats.get("Medium", 0.0)
            hard_beat = beats.get("Hard", 0.0)
            embed.add_field(
                name="📊 Percentile (beats)",
                value=(
                    f"🟢 Easy: `{easy_beat:.2f}%`\n"
                    f"🟡 Medium: `{med_beat:.2f}%`\n"
                    f"🔴 Hard: `{hard_beat:.2f}%`"
                ),
                inline=False
            )

        embed.add_field(
            name="⏳ Time-based Progress",
            value=(
                f"📅 Today: `{time_buckets['today']}`\n"
                f"📆 This Week: `{time_buckets['week']}`\n"
                f"🗓️ This Month: `{time_buckets['month']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="🔥 Current Streak",
            value=f"`{streak}` days",
            inline=False
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ProgressTracker(bot))
