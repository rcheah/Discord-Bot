import discord
from discord.ext import commands
import sqlite3

DB_PATH = "data/scrims.db"

# --- Helferfunktionen ---
def fetch_finalized_scrims():
    """Gibt alle finalisierten Scrims ohne Ergebnis zurück"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.hour, m.host, m.opponent, m.created_at,
               s.user_id, s.team
        FROM scrim_meta m
        JOIN scrim s ON s.id = m.id
        WHERE m.finalized=1 AND m.result IS NULL
        ORDER BY m.id
    """)
    rows = cur.fetchall()
    conn.close()

    scrims = {}
    for row in rows:
        key = (row["id"], row["hour"], row["host"], row["opponent"], row["created_at"])
        scrims.setdefault(key, []).append((row["user_id"], row["team"]))
    return scrims

# --- Modal für Punkteingabe ---
class ScoreModal(discord.ui.Modal):
    def __init__(self, scrim_id, own_team_users, opponent_name):
        super().__init__(title=f"Score für Scrim#{scrim_id}")
        self.scrim_id = scrim_id
        self.opponent_name = opponent_name or "Gegner"

        own_text = "\n".join(f"{user} " for user in own_team_users)
        self.add_item(discord.ui.InputText(
            label="Eigene Team-Punkte (Name Punkt)",
            style=discord.InputTextStyle.paragraph,
            value=own_text,
            required=True
        ))

        self.add_item(discord.ui.InputText(
            label=f"{self.opponent_name}-Punkte (optional, Name Punkt)",
            style=discord.InputTextStyle.paragraph,
            placeholder="Name Punkt ...",
            required=False
        ))

    async def callback(self, interaction: discord.Interaction):
        own_scores_text = self.children[0].value.strip()
        opp_scores_text = self.children[1].value.strip()

        def parse_scores(text):
            total = 0
            scores = {}
            for line in text.splitlines():
                parts = line.strip().split()
                if len(parts) != 2:
                    continue
                name, point = parts
                try:
                    point = int(point)
                except ValueError:
                    continue
                scores[name] = point
                total += point
            return scores, total

        own_scores, own_total = parse_scores(own_scores_text)
        opp_scores, opp_total = parse_scores(opp_scores_text) if opp_scores_text else ({}, 984 - own_total)

        total_points = own_total + opp_total
        if total_points != 984:
            await interaction.response.send_message(
                f"⚠️ Summe der Punkte ist {total_points}, muss 984 sein.",
                ephemeral=True
            )
            return

        result_text = f"{own_total} : {opp_total}"
        if own_total > opp_total:
            result_text += " ✅ WIN"
        elif own_total < opp_total:
            result_text += " ❌ LOSE"
        else:
            result_text += " ➖ DRAW"

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE scrim_meta SET result=? WHERE id=?", (result_text, self.scrim_id))
        cur.execute("DELETE FROM scrim_scores WHERE scrim_id=?", (self.scrim_id,))

        for name, points in own_scores.items():
            member = discord.utils.find(lambda m: m.display_name == name, interaction.guild.members)
            if member:
                cur.execute(
                    "INSERT INTO scrim_scores (scrim_id, user_id, name, team, points) VALUES (?, ?, ?, ?, ?)",
                    (self.scrim_id, str(member.id), member.display_name, "own", points)
                )
            else:
                cur.execute(
                    "INSERT INTO scrim_scores (scrim_id, user_id, name, team, points) VALUES (?, NULL, ?, ?, ?)",
                    (self.scrim_id, name, "own", points)
                )

        for name, points in opp_scores.items():
            cur.execute(
                "INSERT INTO scrim_scores (scrim_id, user_id, name, team, points) VALUES (?, NULL, ?, ?, ?)",
                (self.scrim_id, name, "opponent", points)
            )

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"Score für Scrim#{self.scrim_id}",
            description=result_text,
            color=discord.Color.green() if own_total > opp_total else discord.Color.red()
        )

        own_lines = "\n".join([f"{name} ({points})" for name, points in own_scores.items()])
        opp_lines = "\n".join([f"{name} ({points})" for name, points in opp_scores.items()]) if opp_scores else "Automatisch verrechnet"

        embed.add_field(name="Unser Team", value=own_lines, inline=True)
        embed.add_field(name=self.opponent_name, value=opp_lines, inline=True)

        await interaction.response.send_message(embed=embed)

# --- Select für Scrim-Auswahl ---
class ScrimSelect(discord.ui.Select):
    def __init__(self, scrims, guild):
        options = []
        self.scrims_map = {}
        self.guild = guild
        for (scrim_id, hour, host, opponent, created_at), users in scrims.items():
            display_names = []
            for uid, team in users:
                try:
                    member = guild.get_member(int(uid))
                    display_names.append(member.display_name if member else str(uid))
                except:
                    display_names.append(str(uid))
            label = f"Scrim#{scrim_id} {host} vs {opponent} am {created_at} um {hour} Uhr"
            self.scrims_map[label] = (scrim_id, display_names, opponent)
            options.append(discord.SelectOption(label=label, value=label))
        super().__init__(placeholder="Wähle einen Scrim aus", options=options)

    async def callback(self, interaction: discord.Interaction):
        label = self.values[0]
        scrim_id, display_names, opponent_name = self.scrims_map[label]
        modal = ScoreModal(scrim_id, display_names, opponent_name)
        await interaction.response.send_modal(modal)

class ScrimSelectView(discord.ui.View):
    def __init__(self, scrims, guild):
        super().__init__(timeout=None)
        self.add_item(ScrimSelect(scrims, guild))

# --- Cog ---
class Score(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Pycord-Slash-Command
    @commands.slash_command(
        name="score",
        description="Trage Punkte für einen finalisierten Scrim ein"
    )
    async def score(self, ctx: discord.ApplicationContext):
        scrims = fetch_finalized_scrims()
        if not scrims:
            await ctx.respond("⚠️ Keine finalisierten Scrims ohne Ergebnis gefunden.", ephemeral=True)
            return

        view = ScrimSelectView(scrims, ctx.guild)
        await ctx.respond("Bitte wähle einen Scrim aus:", view=view, ephemeral=True)

# --- async setup ---
async def setup(bot: commands.Bot):
    await bot.add_cog(Score(bot))
