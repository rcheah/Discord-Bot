import discord
from discord.ext import commands
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/scrims.db"

# --- Hilfsfunktionen ---
def fetch_open_scrims():
    """Gibt Scrims zurück, die finalisiert, aber noch kein Ergebnis haben"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.created_at, s.hour, s.team, s.user_id, s.role, m.opponent
        FROM scrim_meta m
        JOIN scrim s ON s.id = m.id
        WHERE m.result IS NULL
        ORDER BY m.id
    """)
    rows = cur.fetchall()
    conn.close()

    scrims = {}
    for row in rows:
        key = (row["id"], row["hour"], row["team"], row["opponent"], row["created_at"])
        scrims.setdefault(key, []).append((row["user_id"], row["role"]))
    return scrims

# --- Modal für Ergebnis ---
class ResultModal(discord.ui.Modal):
    def __init__(self, scrim_id, own_team, opponent, lu_line):
        super().__init__(title=f"Ergebnis für Scrim#{scrim_id}")
        self.scrim_id = scrim_id
        self.own_team = own_team
        self.opponent = opponent or "Gegner"
        self.lu_line = lu_line

        self.add_item(discord.ui.InputText(
            label=f"Punkte {self.own_team}",
            placeholder="Eigene Punkte eingeben",
            required=True
        ))
        self.add_item(discord.ui.InputText(
            label=f"Punkte {self.opponent}",
            placeholder=f"Optional (default: 984 minus eigene Punkte)",
            required=False
        ))

    async def callback(self, interaction: discord.Interaction):
        # Eigene Punkte
        try:
            own_points = int(self.children[0].value.strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Bitte gültige Zahl für eigene Punkte eingeben.", ephemeral=True)
            return

        # Gegnerpunkte
        opponent_input = self.children[1].value.strip()
        if not opponent_input:
            opponent_points = 984 - own_points
        else:
            try:
                opponent_points = int(opponent_input)
            except ValueError:
                await interaction.response.send_message("⚠️ Bitte gültige Zahl für Gegnerpunkte eingeben.", ephemeral=True)
                return

        # Ergebnis berechnen
        diff = abs(own_points - opponent_points)
        if own_points > opponent_points:
            result_text = f"{self.own_team} {own_points} - {self.opponent} {opponent_points} ✅ (+{diff})"
        elif own_points < opponent_points:
            result_text = f"{self.own_team} {own_points} - {self.opponent} {opponent_points} ❌ (-{diff})"
        else:
            result_text = f"{self.own_team} {own_points} - {self.opponent} {opponent_points} ⚠️ (±0)"

        # In DB speichern
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE scrim_meta SET result=? WHERE id=?", (result_text, self.scrim_id))
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ Ergebnis für Scrim#{self.scrim_id} gespeichert:\n{result_text}\nLU: {self.lu_line}",
            ephemeral=True
        )

# --- Select für Scrim-Auswahl ---
class ScrimSelect(discord.ui.Select):
    def __init__(self, scrims):
        options = []
        self.scrims_map = {}
        for (scrim_id, hour, team, opponent, created_at), users in scrims.items():
            # LU-Zeile für Anzeige
            lu_line = ", ".join(
                f"<@{uid}>" for uid, _ in sorted(users, key=lambda x: x[0])
            )
            label = f"Scrim#{scrim_id} {team} am {created_at} um {hour} Uhr"
            self.scrims_map[label] = (scrim_id, team, opponent, lu_line)
            options.append(discord.SelectOption(label=label, value=label))

        super().__init__(placeholder="Wähle einen Scrim aus", options=options)

    async def callback(self, interaction: discord.Interaction):
        label = self.values[0]
        scrim_id, team, opponent, lu_line = self.scrims_map[label]
        modal = ResultModal(scrim_id, team, opponent, lu_line)
        await interaction.response.send_modal(modal)

# --- View für Scrim-Auswahl ---
class ScrimSelectView(discord.ui.View):
    def __init__(self, scrims):
        super().__init__(timeout=None)
        self.add_item(ScrimSelect(scrims))

# --- Cog ---
class Results(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="results",
        description="Trage das Ergebnis eines finalisierten Scrims ein"
    )
    async def results(self, ctx: discord.ApplicationContext):
        scrims = fetch_open_scrims()
        if not scrims:
            await ctx.respond("⚠️ Keine offenen Scrims zum Eintragen von Ergebnissen.", ephemeral=True)
            return

        view = ScrimSelectView(scrims)
        await ctx.respond("Bitte wähle einen Scrim aus:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(Results(bot))
