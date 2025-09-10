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
        self.last_streams = {}

        if not self.client_id or not self.client_secret:
            raise RuntimeError("❌ TWITCH_CLIENT_ID oder TWITCH_CLIENT_SECRET nicht gesetzt!")

        self.check_streams.start()
        asyncio.create_task(self.bot.log("TwitchAlertsCog initialisiert.", "INFO"))

    async def cog_load(self):
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
        await self.bot.log("TwitchAlertsCog: Datenbanktabelle erstellt.", "INFO")

        if not self.bot.get_command("prime"):
            @commands.group(name="prime", invoke_without_command=True)
            async def prime(ctx):
                await ctx.send("Verwende `.prime twitch ...` oder `.prime bank ...`")
            self.bot.add_command(prime)

        prime_cmd = self.bot.get_command("prime")
        if prime_cmd:
            @prime_cmd.group(name="twitch", invoke_without_command=True)
            async def prime_twitch(ctx):
                await ctx.send_help(ctx.command)

            @prime_twitch.command(name="add")
            @commands.has_permissions(manage_guild=True)
            async def twitch_add(ctx, channel_name: str, alert_channel: discord.TextChannel = None):
                alert_channel = alert_channel or ctx.channel
                async with aiosqlite.connect("twitch_alerts.db") as db:
                    try:
                        await db.execute(
                            "INSERT INTO watched_streamers (guild_id, streamer_login, alert_channel_id, added_by) VALUES (?, ?, ?, ?)",
                            (ctx.guild.id, channel_name.lower(), alert_channel.id, ctx.author.id)
                        )
                        await db.commit()
                        await ctx.send(f"✅ Twitch-Streamer **{channel_name}** wird ab jetzt überwacht! Benachrichtigungen in {alert_channel.mention}")
                        await self.bot.log(f"{ctx.author} hat {channel_name} zur Twitch-Überwachung hinzugefügt.", "SUCCESS")
                    except aiosqlite.IntegrityError:
                        await ctx.send(f"❌ **{channel_name}** wird bereits überwacht!")

            @prime_twitch.command(name="list")
            async def twitch_list(ctx):
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
            async def twitch_remove(ctx, channel_name: str):
                async with aiosqlite.connect("twitch_alerts.db") as db:
                    await db.execute(
                        "DELETE FROM watched_streamers WHERE guild_id = ? AND streamer_login = ?",
                        (ctx.guild.id, channel_name.lower())
                    )
                    await db.commit()
                    await ctx.send(f"✅ **{channel_name}** wird nicht mehr überwacht.")
                    await self.bot.log(f"{ctx.author} hat {channel_name} aus der Twitch-Überwachung entfernt.", "INFO")

    def cog_unload(self):
        self.check_streams.cancel()

    async def get_access_token(self):
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
                    await self.bot.log("Twitch Access Token erhalten.", "SUCCESS")
                else:
                    await self.bot.log(f"Twitch Token-Fehler: {data}", "ERROR")

    async def fetch_streams(self, logins):
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
                    await self.bot.log(f"Twitch API-Fehler: {resp.status}", "ERROR")
                    return []
                data = await resp.json()
                return data.get("data", [])

    @tasks.loop(seconds=60)
    async def check_streams(self):
        await self.bot.wait_until_ready()

        streamers_per_guild = {}
        async with aiosqlite.connect("twitch_alerts.db") as db:
            cursor = await db.execute("SELECT guild_id, streamer_login, alert_channel_id FROM watched_streamers")
            rows = await cursor.fetchall()

            for guild_id, streamer_login, alert_channel_id in rows:
                if guild_id not in streamers_per_guild:
                    streamers_per_guild[guild_id] = []
                streamers_per_guild[guild_id].append((streamer_login, alert_channel_id))

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
                        await self.bot.log(f"Twitch-Benachrichtigung für {streamer_login} in Guild {guild_id} gesendet.", "SUCCESS")
                    except Exception as e:
                        await self.bot.log(f"Fehler beim Senden der Twitch-Benachrichtigung: {e}", "ERROR")

                elif not current_stream_id and streamer_login in self.last_streams:
                    del self.last_streams[streamer_login]

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

async def setup(bot):
    await bot.add_cog(TwitchAlertsCog(bot))
    await bot.log("TwitchAlertsCog geladen.", "SUCCESS")