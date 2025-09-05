import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta

BDAY_FILE = "data/bday.json"

def load_birthdays():
    if os.path.exists(BDAY_FILE):
        with open(BDAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

class BdayList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="bday_list", description="Zeige alle gespeicherten Geburtstage (nach nächstem Datum sortiert)")
    async def bday_list(self, ctx: discord.ApplicationContext):
        birthdays = load_birthdays()
        if not birthdays:
            await ctx.respond("❌ Es wurden noch keine Geburtstage gespeichert.", ephemeral=True)
            return

        # Geburtstage auf nächstes Datum anpassen
        today = datetime.now()
        upcoming = []
        for user_id, date_str in birthdays.items():
            try:
                parts = date_str.split(".")
                day = int(parts[0])
                month = int(parts[1])
                year = today.year
                bday_date = datetime(year, month, day)
                if bday_date < today:
                    bday_date = datetime(year + 1, month, day)
                upcoming.append((bday_date, int(user_id), date_str))
            except Exception:
                continue

        # nach Datum sortieren
        upcoming.sort(key=lambda x: x[0])

        msg = "🎉 **Geburtstagsliste:**\n"
        for bday_date, user_id, date_str in upcoming:
            user = ctx.guild.get_member(user_id)
            if user:
                msg += f"- {user.display_name}: {date_str}\n"

        await ctx.respond(msg, ephemeral=True)

def setup(bot):
    bot.add_cog(BdayList(bot))
