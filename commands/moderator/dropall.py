import discord
from discord.ext import commands
from utils import db

class ModDropAll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name = "ada", description = "Entfernt alle Scrims für einen Teilnehmer")
    @commands.has_permissions(administrator = True)
    async def dropall(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(discord.Member, description = "Wähle einen Teilnehmer"), # type: ignore
    ):
        user_id = str(user.id)
        try:
            db.dropall(user_id)
            await ctx.respond(
                f"{user.mention} wurde aus allen Scrims entfernt",
                ephemeral = True,
            )
        except Exception as e:
            await ctx.respond(f"Fehler: {e}", ephemeral = True)

def setup(bot):
    bot.add_cog(ModDropAll(bot))