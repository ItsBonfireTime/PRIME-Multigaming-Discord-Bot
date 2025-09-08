# cogs/twitch_alerts.py
import discord
from discord.ext import commands, tasks
import aiohttp
import aiosqlite
import os
import asyncio
from datetime import datetime

class TwitchAlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv("TWITCH_CLIENT_ID")
        self.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        self.access_token = None
        self.last_streams = {}  # {streamer_login: last_stream_id}

        if not self.client_id or not self.client_secret:
            raise RuntimeError("❌ TWITCH_CLIENT_ID oder TWITCH_CLIENT_SECRET nicht gesetzt!")

        self.check_streams.start()
        print("[TWITCH] TwitchAlertsCog initialisiert.")

    async def cog_load(self):
        """Erstellt die Datenbanktabellen beim Laden des Cogs"""
        async with aiosqlite.connect("twitch_alerts.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watched_streamers (
                    guild_id INTEGER,
                    streamer_login TEXT,
                    alert_channel_id INTEGER,
                    added_by INTEGER,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, streamer_login)
                )
            """)
            await db.commit()
        print("[TWITCH] Datenbanktabelle 'watched_streamers' bereit.")

    def cog_unload(self):
        self.check_streams.cancel()

    async def get_access_token(self):
        """Holt einen neuen OAuth2-Token von Twitch"""
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) as resp:
                data = await resp.json()
                if resp.status == 200:
                    self.access_token = data["access_token"]
                    print("[TWITCH] Neuer Access Token erhalten.")
                else:
                    print(f"[TWITCH] FEHLER beim Token-Holen: {data}")

    async def fetch_streams(self, logins):
        """Holt Stream-Daten für mehrere Streamer"""
        if not self.access_token:
            await self.get_access_token()
            if not self.access_token:
                return []

        url = "https://api.twitch.tv/helix/streams"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        params = [("user_login", login) for login in logins]

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    print(f"[TWITCH] API-Fehler: {resp.status}")
                    return []
                data = await resp.json()
                return data.get("data", [])

    @tasks.loop(seconds=60)
    async def check_streams(self):
        """Prüft alle 60 Sekunden alle überwachten Streamer"""
        await self.bot.wait_until_ready()

        # Sammle alle eindeutigen Streamer aus allen Servern
        streamers_per_guild = {}
        async with aiosqlite.connect("twitch_alerts.db") as db:
            cursor = await db.execute("SELECT guild_id, streamer_login, alert_channel_id FROM watched_streamers")
            rows = await cursor.fetchall()

            for guild_id, streamer_login, alert_channel_id in rows:
                if guild_id not in streamers_per_guild:
                    streamers_per_guild[guild_id] = []
                streamers_per_guild[guild_id].append((streamer_login, alert_channel_id))

        # Prüfe Streams
        all_streamers = list(set(s[0] for guild in streamers_per_guild.values() for s in guild))
        if not all_streamers:
            return

        streams = await self.fetch_streams(all_streamers)
        current_stream_ids = {stream["user_login"]: stream["id"] for stream in streams}

        for guild_id, streamer_list in streamers_per_guild.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            for streamer_login, alert_channel_id in streamer_list:
                channel = self.bot.get_channel(alert_channel_id)
                if not channel:
                    continue

                current_stream_id = current_stream_ids.get(streamer_login)
                last_stream_id = self.last_streams.get(streamer_login)

                if current_stream_id and current_stream_id != last_stream_id:
                    # NEUER STREAM — sende Benachrichtigung
                    self.last_streams[streamer_login] = current_stream_id

                    stream_data = next((s for s in streams if s["user_login"] == streamer_login), None)
                    if not stream_data:
                        continue

                    user_name = stream_data.get("user_name", streamer_login)
                    game_name = stream_data.get("game_name", "Unbekannt")
                    title = stream_data.get("title", "Kein Titel")
                    viewer_count = stream_data.get("viewer_count", 0)
                    thumbnail_url = stream_data.get("thumbnail_url", "").replace("{width}x{height}", "1280x720")

                    embed = discord.Embed(
                        title=f"🔴 {user_name} ist LIVE!",
                        description=f"**{title}**\n\n🎮 **Spiel:** {game_name}\n👥 **Zuschauer:** {viewer_count}",
                        url=f"https://twitch.tv/{streamer_login}",
                        color=0x9146FF,
                        timestamp=datetime.utcnow()
                    )
                    if thumbnail_url:
                        embed.set_image(url=thumbnail_url)
                    embed.set_footer(text="PRIME-Bot Twitch Alert", icon_url=self.bot.user.display_avatar.url)

                    try:
                        await channel.send(content="@everyone 🎥 **LIVE-BENACHRICHTIGUNG**", embed=embed)
                        print(f"[TWITCH] Benachrichtigung gesendet für {streamer_login} in Guild {guild_id}")
                    except Exception as e:
                        print(f"[TWITCH] Fehler beim Senden: {e}")

                elif not current_stream_id and streamer_login in self.last_streams:
                    # Streamer offline → reset
                    del self.last_streams[streamer_login]

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    @commands.group(name="prime", invoke_without_command=True)
    async def prime(self, ctx):
        """Hauptbefehl für PRIME-Bot Funktionen"""
        await ctx.send("Verwende `.prime twitch add <channel>` oder `.prime twitch list`")

    @prime.group(name="twitch", invoke_without_command=True)
    async def prime_twitch(self, ctx):
        """Verwalte Twitch-Streamer-Benachrichtigungen"""
        await ctx.send_help(ctx.command)

    @prime_twitch.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def twitch_add(self, ctx, channel_name: str, alert_channel: discord.TextChannel = None):
        """Füge einen Twitch-Streamer zur Live-Benachrichtigung hinzu
        
        Beispiel: .prime twitch add itsbonfiretime #stream-benachrichtigungen
        """
        alert_channel = alert_channel or ctx.channel

        async with aiosqlite.connect("twitch_alerts.db") as db:
            try:
                await db.execute(
                    "INSERT INTO watched_streamers (guild_id, streamer_login, alert_channel_id, added_by) VALUES (?, ?, ?, ?)",
                    (ctx.guild.id, channel_name.lower(), alert_channel.id, ctx.author.id)
                )
                await db.commit()
                await ctx.send(f"✅ Twitch-Streamer **{channel_name}** wird ab jetzt überwacht! Benachrichtigungen in {alert_channel.mention}")
            except aiosqlite.IntegrityError:
                await ctx.send(f"❌ **{channel_name}** wird bereits überwacht!")

    @prime_twitch.command(name="list")
    async def twitch_list(self, ctx):
        """Zeigt alle überwachten Twitch-Streamer an"""
        async with aiosqlite.connect("twitch_alerts.db") as db:
            cursor = await db.execute(
                "SELECT streamer_login, alert_channel_id FROM watched_streamers WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            rows = await cursor.fetchall()

            if not rows:
                await ctx.send("ℹ️ Es werden aktuell keine Twitch-Streamer überwacht.")
                return

            embed = discord.Embed(title="📺 Überwachte Twitch-Streamer", color=0x9146FF)
            for streamer_login, channel_id in rows:
                channel = self.bot.get_channel(channel_id)
                embed.add_field(
                    name=streamer_login,
                    value=f"Benachrichtigungen in: {channel.mention if channel else 'Unbekannt'}",
                    inline=False
                )
            await ctx.send(embed=embed)

    @prime_twitch.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def twitch_remove(self, ctx, channel_name: str):
        """Entfernt einen Twitch-Streamer aus der Überwachung"""
        async with aiosqlite.connect("twitch_alerts.db") as db:
            await db.execute(
                "DELETE FROM watched_streamers WHERE guild_id = ? AND streamer_login = ?",
                (ctx.guild.id, channel_name.lower())
            )
            await db.commit()
            await ctx.send(f"✅ **{channel_name}** wird nicht mehr überwacht.")

async def setup(bot):
    await bot.add_cog(TwitchAlertsCog(bot))
    print("[COGS] TwitchAlertsCog (mit Datenbank & Commands) geladen.")