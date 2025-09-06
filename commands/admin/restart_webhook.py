import discord
from discord.ext import commands
import aiohttp
import os
from dotenv import load_dotenv

# --- .env laden ---
load_dotenv()
TOKEN = os.getenv("TOKEN")          # Token aus deiner .env
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Webhook-URL aus deiner .env

# --- Globale Variablen ---
webhook = None
session = aiohttp.ClientSession()

# --- Funktion zum Initialisieren des Webhooks ---
async def init_webhook():
    global webhook
    webhook = discord.Webhook.from_url(WEBHOOK_URL, adapter=discord.AsyncWebhookAdapter(session))

# --- Cog für Webhook Management ---
class WebhookManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Webhook direkt beim Cog-Load initialisieren
        self.bot.loop.create_task(init_webhook())

    @commands.slash_command(
        name="restart_webhook",
        description="Startet den Webhook neu (nur Admins)"
    )
    async def restart_webhook(self, ctx: discord.ApplicationContext):
        if not ctx.author.guild_permissions.administrator:
            await ctx.respond("❌ Du hast keine Berechtigung!", ephemeral=True)
            return
        await init_webhook()
        await ctx.respond("✅ Webhook erfolgreich neu gestartet!", ephemeral=True)

    @commands.slash_command(
        name="test_webhook",
        description="Sendet eine Testnachricht über den Webhook"
    )
    async def test_webhook(self, ctx: discord.ApplicationContext):
        if webhook is None:
            await ctx.respond("❌ Webhook ist nicht initialisiert!", ephemeral=True)
            return
        await webhook.send("Webhook funktioniert!")
        await ctx.respond("Nachricht über den Webhook gesendet!", ephemeral=True)

# --- Bot Setup ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot ist ready! Eingeloggt als {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash Commands erfolgreich synchronisiert!")
    except Exception as e:
        print(f"Fehler beim Synchronisieren der Slash Commands: {e}")

# Cog laden
bot.add_cog(WebhookManager(bot))

# --- Bot starten ---
bot.run(TOKEN)
