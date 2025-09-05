import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
from utils.db import init_db
from webhooks.webhook import webhook_updater

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scrim-bot")

# --- Environment ---
load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
if GUILD_ID is None:
    raise ValueError("GUILD_ID ist nicht in der .env definiert!")
GUILD_ID = int(GUILD_ID)

# --- Intents & Bot ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Initialize DB ---
init_db()

# --- Load Cogs ---
for folder in ["commands", "listeners"]:
    for root, dirs, files in os.walk(folder):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("_"):
                extension = (
                    root.replace("/", ".").replace("\\", ".") + "." + filename[:-3]
                )
                try:
                    bot.load_extension(extension)
                    # Guild-ID an Cog weitergeben, falls Cog es erwartet
                    if hasattr(bot.get_cog("Can"), "__init__"):
                        bot.get_cog("Can").guild_id = GUILD_ID
                    logger.info(f"✅ Loaded extension: {extension}")
                except Exception as e:
                    logger.error(f"❌ Failed to load extension {extension}: {e}")

# --- Example Guild Slash-Command ---
@bot.slash_command(guild_ids=[GUILD_ID], description="Ping Command")
async def ping(ctx):
    await ctx.respond("Pong!")

# --- Events ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} ({bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="Developing..."))
    logger.info(f"✅ Slash-Commands ready on Guild {GUILD_ID}")

    logger.info("✅ Starting webhook updater...")
    bot.loop.create_task(webhook_updater(bot))

# --- Start Bot ---
bot.run(TOKEN)
