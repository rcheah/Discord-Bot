import discord
from discord.ext import commands
import sqlite3
import json

DB_PATH = "data/scrims.db"

def get_user_signups(user_id: str):
    """Gibt alle (team, hour) zurück, bei denen der User angemeldet ist."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT team, hour, role, user_ids FROM signups")
    rows = cur.fetchall()
    conn.close()

    user_signups = []
    for row in rows:
        raw = str(row["user_ids"]).strip()
        if raw.startswith("["):
            try:
                user_list = json.loads(raw)
            except json.JSONDecodeError:
                user_list = []
        else:
            user_list = [x.strip() for x in raw.split(",") if x.strip()]

        if user_id in user_list:
            user_signups.append((row["team"], row["hour"]))

    return user_signups

class Drop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="d", description="Für einen Scrim absagen")
    async def drop(self, ctx: discord.ApplicationContext):
        user_id = str(ctx.author.id)
        signups = get_user_signups(user_id)

        if not signups:
            await ctx.respond("⚠️ Du bist aktuell bei keinem Scrim angemeldet.", ephemeral=True)
            return

        # Auswahlmenü für Team + Stunde
        options = [
            discord.SelectOption(label=f"{hour}:00 {team}", value=f"{hour}|{team}")
            for team, hour in signups
        ]

        select = discord.ui.Select(
            placeholder="Wähle einen Scrim zum Droppen",
            options=options,
            min_values=1,
            max_values=1
        )

        async def select_callback(interaction: discord.Interaction):
            hour_str, team = interaction.data["values"][0].split("|")
            hour = int(hour_str)
            # Drop in der DB
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT user_ids, role FROM signups WHERE hour=? AND team=?", (hour, team))
            row = cur.fetchone()
            if row:
                raw_ids, role = row
                try:
                    user_list = json.loads(raw_ids)
                except json.JSONDecodeError:
                    user_list = [x.strip() for x in raw_ids.split(",") if x.strip()]
                if user_id in user_list:
                    user_list.remove(user_id)
                    cur.execute(
                        "UPDATE signups SET user_ids=? WHERE hour=? AND team=? AND role=?",
                        (json.dumps(user_list), hour, team, role)
                    )
            conn.commit()
            conn.close()
            await interaction.response.edit_message(content=f"✅ {ctx.author.mention} dropped vom Scrim um {hour}:00 für {team}.", view=None)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await ctx.respond("Bitte Scrim auswählen, um abzusagen:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(Drop(bot))
