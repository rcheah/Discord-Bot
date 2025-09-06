import discord
from discord.ext import commands
from utils import db


class Drop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name = "d", description = "Für einen Scrim absagen")
    async def drop(
        self,
        ctx: discord.ApplicationContext,
        team: discord.Option(str, choices = ["🔴 Ruby", "🔵 Sapphire", "🟢 Emerald", "🟠 Mixed", "🟣 MK8D"]), # type: ignore
        hour: discord.Option(int, choices = list(reversed(range(24)))), # type: ignore
    ):
        user_id = str(ctx.author.id)
        try:
            db.drop(team, hour, user_id, )
            await ctx.respond(
                f"{ctx.author.mention} dropped off at {hour}:00 for {team}.",
                ephemeral=True,
            )
        except Exception as e:
            await ctx.respond(f"Error: {e}", ephemeral = True)

def setup(bot):
    bot.add_cog(Drop(bot))