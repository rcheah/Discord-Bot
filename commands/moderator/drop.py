import discord
from discord.ext import commands
import sqlite3
import json

DB_PATH = "data/scrims.db"

# --- Hilfsfunktion: Signups laden ---
def fetch_signups():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT hour, team, role, user_ids FROM signups")
    rows = cur.fetchall()
    conn.close()

    grouped = {}
    for row in rows:
        key = (row["hour"], row["team"])
        if key not in grouped:
            grouped[key] = []

        try:
            user_list = json.loads(row["user_ids"])
        except json.JSONDecodeError:
            user_list = [u.strip() for u in str(row["user_ids"]).split(",") if u.strip()]

        for uid in user_list:
            grouped[key].append(uid)
    return grouped

# --- UI Elemente ---
class UserSelect(discord.ui.Select):
    def __init__(self, guild, hour, team, users):
        options = []
        for uid in users:
            try:
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"Unknown({uid})"
            except ValueError:
                name = f"Unknown({uid})"
            options.append(discord.SelectOption(label=name, value=uid))
        super().__init__(placeholder="Wähle einen User zum Entfernen", options=options)
        self.hour = hour
        self.team = team

    async def callback(self, interaction: discord.Interaction):
        uid = self.values[0]
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # User aus Signups entfernen
        cur.execute(
            "SELECT user_ids FROM signups WHERE hour=? AND team=?",
            (self.hour, self.team)
        )
        row = cur.fetchone()
        if row:
            try:
                user_list = json.loads(row[0])
            except json.JSONDecodeError:
                user_list = [x.strip() for x in str(row[0]).split(",") if x.strip()]
            if uid in user_list:
                user_list.remove(uid)
                cur.execute(
                    "UPDATE signups SET user_ids=? WHERE hour=? AND team=?",
                    (json.dumps(user_list), self.hour, self.team)
                )
        conn.commit()
        conn.close()

        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass

        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"Unknown({uid})"
        await interaction.response.send_message(
            f"✅ {name} wurde von {self.team} um {self.hour}:00 entfernt.",
            ephemeral=True
        )

class HourTeamSelect(discord.ui.Select):
    def __init__(self, guild, grouped):
        options = []
        for (hour, team), users in grouped.items():
            if users:  # nur Teams/Stunden mit Spielern
                options.append(discord.SelectOption(label=f"{hour}:00 {team}", value=f"{hour}|{team}"))
        super().__init__(placeholder="Team und Stunde wählen", options=options)
        self.grouped = grouped
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        hour_str, team = self.values[0].split("|")
        hour = int(hour_str)
        users = self.grouped.get((hour, team), [])
        if not users:
            await interaction.response.send_message("⚠️ Keine Spieler in diesem Team.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(UserSelect(self.guild, hour, team, users))
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        await interaction.response.send_message(
            "Wähle den Spieler aus, der entfernt werden soll:",
            view=view,
            ephemeral=True
        )

# --- Cog ---
class ModDrop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="ad", description="Remove certain user of a scrim")
    @commands.has_permissions(administrator=True)
    async def drop(self, ctx: discord.ApplicationContext):
        grouped = fetch_signups()
        if not grouped:
            await ctx.respond("⚠️ Keine Signups gefunden.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(HourTeamSelect(ctx.guild, grouped))
        await ctx.respond("Bitte Team und Stunde auswählen:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(ModDrop(bot))
