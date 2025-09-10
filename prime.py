# prime.py
import discord
import os
import asyncio
import json
import aiohttp.web as web
import jinja2
import aiohttp_jinja2
from datetime import datetime, timedelta, timezone  # 🔹 timezone importiert
import aiosqlite
import sys
from discord.ext import commands

# Lade Konfiguration
try:
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
    print("[SYSTEM] Konfiguration geladen.")
except FileNotFoundError:
    raise RuntimeError("❌ config.json nicht gefunden!")
except json.JSONDecodeError:
    raise RuntimeError("❌ config.json ist ungültig!")

TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", ".")
TEMP_CHANNEL_ID = os.getenv("TEMP_CHANNEL_ID", "1414304729244106833")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 1234))
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", None)

if not TOKEN:
    raise RuntimeError("❌ TOKEN nicht gesetzt!")

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
bot.TEMP_CHANNEL_ID = TEMP_CHANNEL_ID
bot.config = CONFIG
bot.start_time = datetime.now(timezone.utc)  # 🔹 Korrektur hier

# Globaler Logger
async def log_to_channel(message: str, level: str = "INFO"):
    log_channel_id = bot.config["channels"]["log_channel"]
    log_channel = bot.get_channel(log_channel_id)
    if log_channel:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")  # 🔹 Korrektur hier
        emoji = "✅" if level == "SUCCESS" else "⚠️" if level == "WARNING" else "❌" if level == "ERROR" else "ℹ️"
        try:
            await log_channel.send(f"`[{now}]` {emoji} **{level}**: {message}")
        except Exception as e:
            print(f"[LOG FEHLER] Kann nicht in Log-Channel senden: {e}")
    print(f"[{level}] {message}")

bot.log = log_to_channel

# Dashboard Web-App
app = web.Application()
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("dashboard/templates"))

# Session Storage
app['admin_sessions'] = set()

async def login_handler(request):
    if request.method == "POST":
        data = await request.post()
        password = data.get("password")
        if password == DASHBOARD_PASSWORD:
            session_id = str(hash(password + str(datetime.now(timezone.utc))))  # 🔹 Korrektur hier
            app['admin_sessions'].add(session_id)
            response = web.HTTPFound("/admin")
            response.set_cookie("admin_session", session_id, max_age=3600)
            return response
        else:
            context = {"error": "Falsches Passwort!"}
            response = aiohttp_jinja2.render_template("login.html", request, context)
            return response
    else:
        context = {}
        response = aiohttp_jinja2.render_template("login.html", request, context)
        return response

async def admin_handler(request):
    session_id = request.cookies.get("admin_session")
    if not session_id or session_id not in app['admin_sessions']:
        return web.HTTPFound("/login")

    guilds = [{"id": g.id, "name": g.name} for g in bot.guilds]
    uptime = str(datetime.now(timezone.utc) - bot.start_time).split(".")[0]  # 🔹 Korrektur hier

    context = {
        "guilds": guilds,
        "uptime": uptime,
        "server_name": bot.guilds[0].name if bot.guilds else "Kein Server",
        "python_version": sys.version
    }

    response = aiohttp_jinja2.render_template("admin.html", request, context)
    return response

async def logout_handler(request):
    session_id = request.cookies.get("admin_session")
    if session_id in app['admin_sessions']:
        app['admin_sessions'].remove(session_id)
    response = web.HTTPFound("/")
    response.del_cookie("admin_session")
    return response

async def dashboard_handler(request):
    # Top 10 Level
    top_level = []
    try:
        async with aiosqlite.connect("leveling.db") as db:
            async with db.execute("SELECT user_id, xp, level FROM users ORDER BY level DESC, xp DESC LIMIT 10") as cursor:
                async for row in cursor:
                    user = bot.get_user(row[0]) or await bot.fetch_user(row[0])
                    top_level.append({
                        "name": user.display_name if user else f"User {row[0]}",
                        "xp": row[1],
                        "level": row[2]
                    })
    except Exception as e:
        await bot.log(f"Fehler beim Laden von Top Level: {e}", "ERROR")

    # Top 10 Coins
    top_coins = []
    try:
        async with aiosqlite.connect("economy.db") as db:
            async with db.execute("SELECT user_id, balance FROM coins ORDER BY balance DESC LIMIT 10") as cursor:
                async for row in cursor:
                    user = bot.get_user(row[0]) or await bot.fetch_user(row[0])
                    top_coins.append({
                        "name": user.display_name if user else f"User {row[0]}",
                        "balance": row[1]
                    })
    except Exception as e:
        await bot.log(f"Fehler beim Laden von Top Coins: {e}", "ERROR")

    # Aktive Twitch-Streamer
    active_streamers = []
    try:
        twitch_cog = bot.get_cog("TwitchAlertsCog")
        if twitch_cog and hasattr(twitch_cog, 'last_streams'):
            for streamer_login in twitch_cog.last_streams.keys():
                active_streamers.append({
                    "user_name": streamer_login,
                    "game_name": "Live",
                    "viewer_count": "N/A"
                })
    except Exception as e:
        await bot.log(f"Fehler beim Laden von Twitch-Streamern: {e}", "ERROR")

    # Nächste Geburtstage
    upcoming_birthdays = []
    try:
        birthday_cog = bot.get_cog("BirthdayManagerCog")
        if birthday_cog:
            birthdays = birthday_cog.load_birthdays()
            today = datetime.now(timezone.utc).date()  # 🔹 Korrektur hier
            week_end = today + timedelta(days=7)
            for user_id_str, data in birthdays.items():
                day, month, year = map(int, data["date"].split("."))
                this_year_bday = today.replace(month=month, day=day)
                next_bday = this_year_bday if this_year_bday >= today else today.replace(year=today.year + 1, month=month, day=day)
                if today <= next_bday <= week_end:
                    user = bot.get_user(int(user_id_str)) or await bot.fetch_user(int(user_id_str))
                    name = user.display_name if user else data["name"]
                    days_until = (next_bday - today).days
                    upcoming_birthdays.append({
                        "name": name,
                        "date": data["date"],
                        "days_until": days_until
                    })
            upcoming_birthdays.sort(key=lambda x: x["days_until"])
    except Exception as e:
        await bot.log(f"Fehler beim Laden von Geburtstagen: {e}", "ERROR")

    server_name = bot.guilds[0].name if bot.guilds else "PRIME-Server"
    uptime = str(datetime.now(timezone.utc) - bot.start_time).split(".")[0]  # 🔹 Korrektur hier

    context = {
        "top_level": top_level,
        "top_coins": top_coins,
        "active_streamers": active_streamers,
        "upcoming_birthdays": upcoming_birthdays,
        "server_name": server_name,
        "uptime": uptime
    }

    response = aiohttp_jinja2.render_template("index.html", request, context)
    return response

# Routes
app.router.add_get("/", dashboard_handler)
app.router.add_get("/login", login_handler)
app.router.add_post("/login", login_handler)
app.router.add_get("/admin", admin_handler)
app.router.add_get("/logout", logout_handler)

async def start_dashboard():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", DASHBOARD_PORT)
    await site.start()
    await bot.log(f"Dashboard läuft auf Port {DASHBOARD_PORT}", "SUCCESS")

@bot.event
async def on_ready():
    await bot.log(f"Bot eingeloggt als {bot.user} ({bot.user.id})", "SUCCESS")
    asyncio.create_task(start_dashboard())

    cogs = [
        "cogs.leveling",
        "cogs.voice_manager",
        "cogs.prime_economy",
        "cogs.twitch_alerts",
        "cogs.slots_game",
        "cogs.duel_game",
        "cogs.roulette_game",
        "cogs.birthday_manager"
    ]

    await bot.change_presence(activity=discord.Game("Von Gamern. Für Gamer."))

    for cog in cogs:
        try:
            await bot.load_extension(cog)
            await bot.log(f"{cog} geladen.", "SUCCESS")
        except Exception as e:
            await bot.log(f"Fehler beim Laden von {cog}: {e}", "ERROR")

    await bot.log("Bot ist bereit!", "SUCCESS")

bot.run(TOKEN)