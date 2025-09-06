import discord
from discord.ext import commands
import sqlite3
from collections import Counter

DB_PATH = "data/scrims.db"

TEAM_EMOJIS = {
    "🔴 Ruby": "🔴",
    "🔵 Sapphire": "🔵",
    "🟢 Emerald": "🟢",
    "🟠 Mixed": "🟠",
    "🟣 MK8D": "🟣"
}

# ---------------- Spieler Stats ----------------
def fetch_user_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT SUM(points), COUNT(*)
        FROM scrim_scores
        WHERE user_id=?
    """, (str(user_id),))
    row = cur.fetchone()
    total_points, total_games = row if row else (0, 0)

    cur.execute("""
        SELECT m.result_status
        FROM scrim_meta m
        JOIN scrim_scores s ON m.id = s.scrim_id
        WHERE s.user_id=?
    """, (str(user_id),))
    rows = cur.fetchall()
    wins = sum(1 for r in rows if r[0] == 'win')
    losses = sum(1 for r in rows if r[0] == 'lose')

    conn.close()
    if total_games == 0:
        return None

    return {
        "games": total_games,
        "wins": wins,
        "losses": losses,
        "points": total_points,
        "winrate": round((wins / total_games) * 100, 1)
    }

# ---------------- Team Stats ----------------
def fetch_team_stats(team):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT SUM(team_points), SUM(opponent_points), COUNT(*)
        FROM scrim_meta
        WHERE team=?
          AND finalized=1
    """, (team,))
    row = cur.fetchone()
    if not row or row[2] == 0:
        conn.close()
        return None

    team_points, opponent_points, games = row
    diff = team_points - opponent_points
    winrate = round((team_points / max(1, team_points + opponent_points)) * 100, 1)
    conn.close()

    return {
        "games": games,
        "points_for": team_points,
        "points_against": opponent_points,
        "diff": diff,
        "winrate": winrate
    }

# ---------------- Scrim Details ----------------
def fetch_scrim(scrim_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, created_at, team, opponent, team_points, opponent_points, finalized, result_status
        FROM scrim_meta
        WHERE id=?
    """, (scrim_id,))
    meta = cur.fetchone()
    if not meta:
        conn.close()
        return None

    cur.execute("""
        SELECT user_id, name, team, points
        FROM scrim_scores
        WHERE scrim_id=?
    """, (scrim_id,))
    players = cur.fetchall()
    conn.close()

    return {
        "meta": {
            "id": meta[0],
            "created_at": meta[1],
            "team": meta[2],
            "opponent": meta[3],
            "team_points": meta[4],
            "opponent_points": meta[5],
            "finalized": meta[6],
            "result_status": meta[7]
        },
        "players": [{"user_id": p[0], "name": p[1], "team": p[2], "points": p[3]} for p in players]
    }

# ---------------- Leaderboard ----------------
def fetch_leaderboard(limit=5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, SUM(points) as total_points, COUNT(*) as matches
        FROM scrim_scores
        GROUP BY user_id
        ORDER BY total_points DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()

    leaderboard = []
    for user_id, total_points, matches in rows:
        avg_points = round(total_points / matches, 1) if matches > 0 else 0

        cur.execute("""
            SELECT team
            FROM scrim_scores
            WHERE user_id=?
        """, (user_id,))
        teams = [r[0] for r in cur.fetchall()]
        main_team = Counter(teams).most_common(1)[0][0] if teams else None
        team_emoji = TEAM_EMOJIS.get(main_team, "❔")

        leaderboard.append({
            "user_id": user_id,
            "total_points": total_points,
            "matches": matches,
            "avg_points": avg_points,
            "team_emoji": team_emoji
        })

    conn.close()
    return leaderboard

# ---------------- Cog ----------------
class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="stats",
        description="Zeigt Spieler-, Team- oder Scrim-Statistiken an"
    )
    async def stats(self, ctx: discord.ApplicationContext,
                    user: discord.Member = None,
                    team: str = None,
                    scrim_id: int = None):
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
            embed.add_field(name="Punkte", value=str(stats["points"]))
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
            embed.add_field(name="Punkte", value=f"{stats['points_for']} : {stats['points_against']}")
            embed.add_field(name="Differenz", value=str(stats["diff"]))
            embed.add_field(name="Winrate", value=f"{stats['winrate']}%")
            await ctx.respond(embed=embed)

        elif scrim_id:
            scrim = fetch_scrim(scrim_id)
            if not scrim:
                await ctx.respond(f"⚠️ Kein Scrim mit ID {scrim_id} gefunden.", ephemeral=True)
                return
            meta = scrim["meta"]
            embed = discord.Embed(
                title=f"📋 Scrim #{meta['id']}: {meta['team']} vs {meta['opponent']}",
                description=f"Ergebnis: {meta['team_points']} : {meta['opponent_points']}\nFinalisiert: {meta['finalized']}",
                color=discord.Color.orange()
            )
            for player in scrim["players"]:
                embed.add_field(name=f"{player['name']} {TEAM_EMOJIS.get(player['team'], '❔')}",
                                value=f"Team: {player['team']} | Punkte: {player['points']}", inline=False)
            await ctx.respond(embed=embed)

        else:
            # Top-5 Leaderboard
            top_players = fetch_leaderboard()
            if not top_players:
                await ctx.respond("⚠️ Noch keine Scrims eingetragen.", ephemeral=True)
                return

            desc = ""
            for rank, p in enumerate(top_players, start=1):
                member = ctx.guild.get_member(int(p["user_id"]))
                name = member.display_name if member else f"Unknown({p['user_id']})"
                desc += f"**#{rank} {name} {p['team_emoji']}** — {p['total_points']} Punkte | Matches: {p['matches']} | Ø: {p['avg_points']}\n"

            embed = discord.Embed(
                title="🏆 Top 5 Spieler Leaderboard",
                description=desc,
                color=discord.Color.gold()
            )
            await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Stats(bot))
