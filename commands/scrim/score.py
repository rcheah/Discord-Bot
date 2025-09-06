import discord
from discord.ext import commands
import sqlite3

DB_PATH = "data/scrims.db"

# --- Helferfunktionen ---
def fetch_finalized_scrims():
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

# --- Modal für Punkteingabe mit Sicherheitsabfrage ---
class ScoreModal(discord.ui.Modal):
    def __init__(self, scrim_id, own_team_users, opponent_name, own_value="", opp_value=""):
        super().__init__(title=f"Punkte für Scrim#{scrim_id}")
        self.scrim_id = scrim_id
        self.opponent_name = opponent_name or "Gegner"

        self.add_item(discord.ui.InputText(
            label="Team-Punkte WEC (Name: Punkt)",
            style=discord.InputTextStyle.paragraph,
            value=own_value or "\n".join(f"{user}: " for user in own_team_users),
            required=True
        ))
        self.add_item(discord.ui.InputText(
            label=f"{self.opponent_name}-Punkte (optional, Name: Punkt)",
            style=discord.InputTextStyle.paragraph,
            value=opp_value,
            required=False
        ))

    async def callback(self, interaction: discord.Interaction):
        own_scores_text = self.children[0].value.strip()
        opp_scores_text = self.children[1].value.strip()

        def parse_scores(text):
            total = 0
            scores = {}
            for line in text.splitlines():
                line = line.strip()
                if ": " not in line:
                    continue
                name, point_str = line.rsplit(": ", 1)
                try:
                    point = int(point_str)
                except ValueError:
                    continue
                scores[name] = point
                total += point
            return scores, total

        own_scores, own_total = parse_scores(own_scores_text)
        opp_scores, opp_total = parse_scores(opp_scores_text) if opp_scores_text else ({}, 984 - own_total)

        if own_total + opp_total != 984:
            view = discord.ui.View(timeout=None)
            class ConfirmButton(discord.ui.Button):
                def __init__(self, confirm: bool):
                    super().__init__(label="Ja" if confirm else "Nein",
                                     style=discord.ButtonStyle.green if confirm else discord.ButtonStyle.red)
                    self.confirm = confirm

                async def callback(self2, i: discord.Interaction):
                    if self2.confirm:
                        await self.save_scores(i, own_scores, opp_scores, own_total, opp_total)
                    else:
                        new_modal = ScoreModal(
                            self.scrim_id,
                            own_team_users=list(own_scores.keys()),
                            opponent_name=self.opponent_name,
                            own_value=own_scores_text,
                            opp_value=opp_scores_text
                        )
                        await i.response.send_modal(new_modal)
                    view.stop()

            view.add_item(ConfirmButton(True))
            view.add_item(ConfirmButton(False))
            await interaction.response.send_message(
                f"Die Summe der Punkte ist {own_total + opp_total}, nicht 984. Trotzdem speichern?",
                view=view,
                ephemeral=True
            )
            return

        await self.save_scores(interaction, own_scores, opp_scores, own_total, opp_total)

    async def save_scores(self, interaction, own_scores, opp_scores, own_total, opp_total):
        if own_total > opp_total:
            result_status = "WIN"
            result_text = f"{own_total} : {opp_total} ✅ WIN"
        elif own_total < opp_total:
            result_status = "LOSE"
            result_text = f"{own_total} : {opp_total} ❌ LOSE"
        else:
            result_status = "DRAW"
            result_text = f"{own_total} : {opp_total} ➖ DRAW"

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE scrim_meta 
            SET team_points=?, opponent_points=?, result_status=?, result=? 
            WHERE id=?
        """, (own_total, opp_total, result_status, result_text, self.scrim_id))

        cur.execute("DELETE FROM scrim_scores WHERE scrim_id=?", (self.scrim_id,))

        for name, points in own_scores.items():
            member = discord.utils.find(lambda m: m.display_name == name, interaction.guild.members)
            user_id = str(member.id) if member else None
            cur.execute(
                "INSERT INTO scrim_scores (scrim_id, user_id, name, team, points) VALUES (?, ?, ?, ?, ?)",
                (self.scrim_id, user_id, name, "own", points)
            )

        for name, points in opp_scores.items():
            cur.execute(
                "INSERT INTO scrim_scores (scrim_id, user_id, name, team, points) VALUES (?, ?, ?, ?, ?)",
                (self.scrim_id, None, name, "opponent", points)
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
        embed.add_field(name="WEC", value=own_lines or "Keine Punkte", inline=True)
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
                except Exception:
                    display_names.append(str(uid))
            label = f"Scrim#{scrim_id} WEC vs {opponent} am {created_at} um {hour} Uhr"
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

    @commands.slash_command(
        name="score",
        description="Trage Punkte für einen Scrim ein"
    )
    async def score(self, ctx: discord.ApplicationContext):
        scrims = fetch_finalized_scrims()
        if not scrims:
            await ctx.respond("Keine Scrims ohne Ergebnis gefunden!", ephemeral=True)
            return

        view = ScrimSelectView(scrims, ctx.guild)
        await ctx.respond("Bitte wähle einen Scrim aus:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(Score(bot))
