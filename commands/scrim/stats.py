import discord
from discord.ext import commands
import sqlite3

DB_PATH = "data/scrims.db"

def fetch_user_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT SUM(points_for), SUM(points_against), SUM(win), COUNT(*)
        FROM scrim_stats
        WHERE user_id=?
    """, (str(user_id),))
    row = cur.fetchone()
    conn.close()
    if not row or row[3] == 0:
        return None
    points_for, points_against, wins, total = row
    losses = total - wins
    winrate = round((wins / total) * 100, 1)
    diff = (points_for or 0) - (points_against or 0)
    return {
        "games": total,
        "wins": wins,
        "losses": losses,
        "points_for": points_for or 0,
        "points_against": points_against or 0,
        "diff": diff,
        "winrate": winrate,
    }

def fetch_team_stats(team):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT SUM(points_for), SUM(points_against), SUM(win), COUNT(*)
        FROM scrim_stats
        WHERE team=?
    """, (team,))
    row = cur.fetchone()
    conn.close()
    if not row or row[3] == 0:
        return None
    points_for, points_against, wins, total = row
    losses = total - wins
    winrate = round((wins / total) * 100, 1)
    diff = (points_for or 0) - (points_against or 0)
    return {
        "games": total,
        "wins": wins,
        "losses": losses,
        "points_for": points_for or 0,
        "points_against": points_against or 0,
        "diff": diff,
        "winrate": winrate,
    }

def fetch_leaderboard(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, COUNT(*)
        FROM scrim_stats
        GROUP BY user_id
        ORDER BY COUNT(*) DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="stats",
        description="Zeigt Statistiken für Spieler oder Teams an"
    )
    async def stats(self, ctx: discord.ApplicationContext,
                    user: discord.Member = None,
                    team: str = None):

        if user:
            stats = fetch_user_stats(user.id)
            if not stats:
                await ctx.respond(f"⚠️ Keine Statistiken für {user.display_name} gefunden.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"📊 Stats für {user.display_name}",
                color=discord.Color.green()
            )
            embed.add_field(name="Scrims", value=str(stats["games"]))
            embed.add_field(name="Wins", value=str(stats["wins"]))
            embed.add_field(name="Losses", value=str(stats["losses"]))
            embed.add_field(name="Winrate", value=f"{stats['winrate']}%")
            embed.add_field(name="Punkte", value=f"{stats['points_for']} : {stats['points_against']}")
            embed.add_field(name="Differenz", value=str(stats["diff"]))
            await ctx.respond(embed=embed)

        elif team:
            stats = fetch_team_stats(team)
            if not stats:
                await ctx.respond(f"⚠️ Keine Statistiken für Team **{team}** gefunden.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"📊 Stats für Team {team}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Scrims", value=str(stats["games"]))
            embed.add_field(name="Wins", value=str(stats["wins"]))
            embed.add_field(name="Losses", value=str(stats["losses"]))
            embed.add_field(name="Winrate", value=f"{stats['winrate']}%")
            embed.add_field(name="Punkte", value=f"{stats['points_for']} : {stats['points_against']}")
            embed.add_field(name="Differenz", value=str(stats["diff"]))
            await ctx.respond(embed=embed)

        else:
            leaderboard = fetch_leaderboard()
            if not leaderboard:
                await ctx.respond("⚠️ Noch keine Scrims eingetragen.", ephemeral=True)
                return

            desc = ""
            for rank, (uid, games) in enumerate(leaderboard, start=1):
                member = ctx.guild.get_member(int(uid))
                name = member.display_name if member else f"Unknown({uid})"
                desc += f"**#{rank}** {name} — {games} Scrims\n"

            embed = discord.Embed(
                title="🏆 Scrim Leaderboard",
                description=desc,
                color=discord.Color.gold()
            )
            await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Stats(bot))
