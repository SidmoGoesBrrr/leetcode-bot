import discord
from discord.ext import commands
import aiohttp
from datetime import datetime, timezone
from graphql_queries import UPCOMING_CONTESTS_QUERY

def format_relative(ts: int) -> str:
    """
    Given a UNIX timestamp (seconds), return a relative-time string.
    If ts is in the future: "in 2d 3h 15m"
    If ts is in the past:   "• 1d 6h ago"
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    diff = ts - now_ts

    if diff > 0:
        seconds = int(diff)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return "in " + " ".join(parts)
    else:
        seconds = int(-diff)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return "• " + " ".join(parts) + " ago"


class UpcomingContests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="contest")
    async def upcoming(self, ctx):
        """
        Usage: !contest
        Fetches LeetCode’s upcoming contests via GraphQL and sends an embed.
        """
        async with aiohttp.ClientSession() as session:
            payload = {"query": UPCOMING_CONTESTS_QUERY}
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
            async with session.post("https://leetcode.com/graphql", json=payload, headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send("⚠️ Failed to fetch upcoming contests.")
                    return
                result = await resp.json()

        contests = result.get("data", {}).get("upcomingContests", [])
        if not contests:
            await ctx.send("ℹ️ No upcoming contests found.")
            return

        # Build embed
        embed = discord.Embed(
            title="🚀 Upcoming LeetCode Contests",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url="https://leetcode.com/static/images/LeetCode_logo_rvs.png")

        for c in sorted(contests, key=lambda c: int(c["startTime"])):
            title = c["title"]
            start_ts = int(c["startTime"])
            rel = format_relative(start_ts)
            dur_sec = int(c["duration"])
            hrs, rem = divmod(dur_sec, 3600)
            mins = rem // 60
            dur_text = f"{hrs}h {mins}m" if hrs else f"{mins}m"

            embed.add_field(
                name=title,
                value=f"Starts {rel}\nDuration: `{dur_text}`",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(UpcomingContests(bot))