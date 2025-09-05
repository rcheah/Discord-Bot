import discord
from discord.ext import commands
import json
import os

BDAY_FILE = "data/bday.json"

def load_birthdays():
    if os.path.exists(BDAY_FILE):
        with open(BDAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_birthdays(birthdays):
    with open(BDAY_FILE, "w", encoding="utf-8") as f:
        json.dump(birthdays, f, indent=4, ensure_ascii=False)

class BdayRemove(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="bday_remove",
        description="Lösche deinen gespeicherten Geburtstag oder als Admin den Geburtstag eines anderen Nutzers"
    )
    async def bday_remove(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, required=False, description="Optional: Geburtstag eines anderen Nutzers löschen")
    ):
        birthdays = load_birthdays()

        # Zielnutzer bestimmen
        target = user if user else ctx.author
        user_id = str(target.id)

        # Admin-Check: andere nur erlaubt, wenn ctx.author Administrator ist
        if user and user != ctx.author and not ctx.author.guild_permissions.administrator:
            await ctx.respond("❌ Du hast keine Berechtigung, den Geburtstag anderer Nutzer zu löschen.", ephemeral=True)
            return

        if user_id in birthdays:
            del birthdays[user_id]
            save_birthdays(birthdays)
            if target == ctx.author:
                await ctx.respond("✅ Dein Geburtstag wurde gelöscht.", ephemeral=True)
            else:
                await ctx.respond(f"✅ Geburtstag von {target.display_name} wurde gelöscht.", ephemeral=True)
        else:
            await ctx.respond("❌ Es wurde kein gespeicherter Geburtstag gefunden.", ephemeral=True)

def setup(bot):
    bot.add_cog(BdayRemove(bot))
