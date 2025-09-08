# cogs/leveling.py
import discord
from discord.ext import commands
import aiosqlite
import random
from datetime import datetime, timedelta

class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}  # {user_id: last_message_time}

    async def cog_load(self):
        """Wird beim Laden des Cogs ausgeführt — erstellt DB-Tabelle"""
        async with aiosqlite.connect("leveling.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    last_message DATETIME
                )
            """)
            await db.commit()
        print("[LEVELING] Datenbanktabelle 'users' wurde erstellt/überprüft.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        user_id = message.author.id
        now = datetime.utcnow()

        # Cooldown: Nur alle 60 Sekunden XP geben
        if user_id in self.cooldowns:
            last_msg = self.cooldowns[user_id]
            if now - last_msg < timedelta(seconds=60):
                return

        self.cooldowns[user_id] = now

        # XP vergeben (5-15 XP)
        xp_gain = random.randint(5, 15)

        async with aiosqlite.connect("leveling.db") as db:
            # Hole aktuellen XP-Stand
            cursor = await db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()

            if not row:
                # Neuer Benutzer
                await db.execute(
                    "INSERT INTO users (user_id, xp, level, last_message) VALUES (?, ?, ?, ?)",
                    (user_id, xp_gain, 1, now.isoformat())
                )
                new_xp = xp_gain
                new_level = 1
            else:
                current_xp, current_level = row
                new_xp = current_xp + xp_gain

                # Level-Up-Formel: level = floor(sqrt(xp) / 10) + 1
                new_level = int(new_xp ** 0.5 / 10) + 1

                if new_level > current_level:
                    # Level-Up!
                    await message.channel.send(
                        f"🎉 **Level Up!** {message.author.mention} ist jetzt Level **{new_level}**!",
                        delete_after=10
                    )

                await db.execute(
                    "UPDATE users SET xp = ?, level = ?, last_message = ? WHERE user_id = ?",
                    (new_xp, new_level, now.isoformat(), user_id)
                )

            await db.commit()

    @commands.command(name="rank", aliases=["level", "profile"])
    async def rank(self, ctx, member: discord.Member = None):
        """Zeigt dein Level und XP an"""
        member = member or ctx.author
        async with aiosqlite.connect("leveling.db") as db:
            cursor = await db.execute("SELECT xp, level FROM users WHERE user_id = ?", (member.id,))
            row = await cursor.fetchone()

            if not row:
                await ctx.send(f"{member.mention} hat noch kein XP gesammelt.")
                return

            xp, level = row
            next_level_xp = ((level + 1) * 10) ** 2  # Umgekehrte Formel
            current_level_xp = (level * 10) ** 2
            xp_needed = next_level_xp - current_level_xp
            xp_current = xp - current_level_xp

            # Fortschrittsbalken
            progress = min(int((xp_current / xp_needed) * 10), 10)
            bar = "🟩" * progress + "⬜" * (10 - progress)

            embed = discord.Embed(
                title=f"📊 Level von {member.display_name}",
                color=discord.Color.gold()
            )
            embed.add_field(name="Level", value=f"**{level}**", inline=True)
            embed.add_field(name="XP", value=f"**{xp_current} / {xp_needed}** bis Level {level + 1}", inline=True)
            embed.add_field(name="Fortschritt", value=bar, inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"User ID: {member.id}")

            await ctx.send(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard(self, ctx):
        """Zeigt die Top 10 User nach Level und XP"""
        async with aiosqlite.connect("leveling.db") as db:
            cursor = await db.execute("""
                SELECT user_id, xp, level
                FROM users
                ORDER BY level DESC, xp DESC
                LIMIT 10
            """)
            rows = await cursor.fetchall()

            if not rows:
                await ctx.send("Noch keine User im Leaderboard.")
                return

            embed = discord.Embed(title="🏆 Leaderboard", color=discord.Color.blue())
            description = ""

            for i, (user_id, xp, level) in enumerate(rows, 1):
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                name = user.display_name if user else f"User {user_id}"
                description += f"`{i}.` **{name}** — Level {level} | {xp} XP\n"

            embed.description = description
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LevelingCog(bot))