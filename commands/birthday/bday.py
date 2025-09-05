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

class Bday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="bday", description="Trage deinen Geburtstag ein")
    async def bday(
        self,
        ctx: discord.ApplicationContext,
        date: discord.Option(str, description="TT.MM. oder TT.MM.YYYY")
    ):
        birthdays = load_birthdays()
        user_id = str(ctx.author.id)
        birthdays[user_id] = date
        save_birthdays(birthdays)
        await ctx.respond(f"✅ Dein Geburtstag wurde gespeichert: {date} 🎉", ephemeral=True)

def setup(bot):
    bot.add_cog(Bday(bot))
