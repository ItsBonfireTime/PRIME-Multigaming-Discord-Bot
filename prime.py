# prime.py
import discord
import os
import asyncio
from datetime import datetime
from discord.ext import commands

# Lese Token und Prefix aus Umgebungsvariablen
TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", ".")
TEMP_CHANNEL_ID = os.getenv("TEMP_CHANNEL_ID", "1414304729244106833")  # Optional: als Variable konfigurierbar machen

if not TOKEN:
    raise RuntimeError("❌ Umgebungsvariable 'TOKEN' nicht gesetzt!")

# Intents
intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.message_content = True

# Bot initialisieren
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# TEMP_CHANNEL_ID als Bot-Attribut speichern (für Cog zugänglich)
bot.TEMP_CHANNEL_ID = TEMP_CHANNEL_ID

def log(message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")

@bot.event
async def on_ready():
    log(f"Bot eingeloggt als {bot.user} ({bot.user.id})")
    
    # Lade Cogs
    try:
        await bot.load_extension("cogs.leveling")
        log("[COGS] Leveling-Cog geladen.")
    except Exception as e:
        log(f"[COGS] Fehler beim Laden von Leveling-Cog: {e}")

    try:
        await bot.load_extension("cogs.voice_manager")
        log("[COGS] VoiceManager-Cog geladen.")
    except Exception as e:
        log(f"[COGS] Fehler beim Laden von VoiceManager-Cog: {e}")
        
    try:
        await bot.load_extension("cogs.twitch_alerts")
        log("[COGS] TwitchAlerts-Cog geladen.")
    except Exception as e:
        log(f"[COGS] Fehler beim Laden von TwitchAlerts-Cog: {e}")

    log("Bot ist bereit!")
    log("------")

# ⚠️ on_voice_state_update wurde ENTFERNT — wird jetzt vom Cog behandelt!

# Bot starten
bot.run(TOKEN)