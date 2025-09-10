# cogs/prime_economy.py
import discord
from discord.ext import commands, tasks
import aiosqlite
import random
import asyncio
from datetime import datetime, timedelta

class PrimeEconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.heist_active = False
        self.heist_participants = {}
        self.heist_end_time = None
        self.bank_balance = 1000
        self.allowed_channel_id = self.bot.config["channels"]["economy"]

    async def cog_load(self):
        async with aiosqlite.connect("economy.db") as db:
            await db.execute("CREATE TABLE IF NOT EXISTS coins (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
            await db.commit()
        await self.bot.log("PrimeEconomyCog: Datenbanktabelle erstellt.", "INFO")
        self.hourly_heist.start()

    def cog_unload(self):
        self.hourly_heist.cancel()

    def check_channel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure(f"❌ Dieser Befehl ist nur im <#{self.allowed_channel_id}> erlaubt!")
        return True

    @commands.group(name="prime", invoke_without_command=True)
    async def prime(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            await ctx.send(f"ℹ️ Economy-Befehle nur im <#{self.allowed_channel_id}> verfügbar!")
            return
        await ctx.send("Verwende `.prime convert`, `.prime bank` oder `.prime heist`")

    @prime.group(name="convert", invoke_without_command=True)
    async def prime_convert(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            return
        await ctx.send_help(ctx.command)

    @prime_convert.command(name="xp")
    async def convert_xp(self, ctx, amount: int):
        self.check_channel(ctx)
        if amount <= 0:
            await ctx.send("❌ Du musst mehr als 0 XP umwandeln!")
            return

        async with aiosqlite.connect("leveling.db") as db:
            cursor = await db.execute("SELECT xp FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            if not row or row[0] < amount:
                await ctx.send("❌ Du hast nicht genug XP!")
                return

            coins = amount // 10
            if coins == 0:
                await ctx.send("❌ Du brauchst mindestens 10 XP für 1 Coin!")
                return

            await db.execute("UPDATE users SET xp = xp - ? WHERE user_id = ?", (amount, ctx.author.id))
            await db.commit()

        async with aiosqlite.connect("economy.db") as db:
            await db.execute("INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (ctx.author.id, coins, coins))
            await db.commit()

        await ctx.send(f"✅ Du hast **{amount} XP** in **{coins} Coins** umgewandelt!")
        await self.bot.log(f"{ctx.author} hat {amount} XP in {coins} Coins umgewandelt.", "SUCCESS")

    # ... (Rest der Befehle wie .bank, .heist — analog mit await self.bot.log(...))

    @tasks.loop(minutes=1)
    async def hourly_heist(self):
        now = datetime.utcnow()
        if now.minute == 0:
            channel = self.bot.get_channel(self.allowed_channel_id)
            if not channel:
                await self.bot.log("Economy-Channel nicht gefunden!", "ERROR")
                return

            if self.heist_active:
                await channel.send("⏳ Ein Heist läuft bereits — überspringe automatischen Start.")
                return

            self.heist_active = True
            self.heist_participants = {}
            self.heist_end_time = now + timedelta(minutes=10)

            await channel.send(
                f"🚨 **AUTOMATISCHER BANKÜBERFALL!** Die PRIME-Bank wird **JETZT** überfallen!\n"
                f"💰 Bankinhalt: **{self.bank_balance} Coins**\n"
                f"⏱️ Du hast **10 Minuten**, um mit `.prime heist join <amount>` teilzunehmen!"
            )
            await self.bot.log("Automatischer Heist gestartet.", "INFO")

            await asyncio.sleep(600)
            await self.resolve_heist(channel)

    @hourly_heist.before_loop
    async def before_hourly_heist(self):
        await self.bot.wait_until_ready()
        now = datetime.utcnow()
        sleep_seconds = (60 - now.minute) * 60 - now.second
        await asyncio.sleep(sleep_seconds)

    async def resolve_heist(self, channel):
        if not self.heist_active:
            return

        self.heist_active = False
        total_bet = sum(self.heist_participants.values())

        if total_bet == 0:
            satirical_messages = [
                "🕵️‍♂️ *Die Bankräuber kamen... aber niemand war da.*",
                "🏦 *Die PRIME-Bank schickte eine Rechnung für 'versuchten Überfall'.*",
                "🦹‍♂️ *Der Meisterdieb flüsterte: 'Wo ist die Crew?' — Stille.*"
            ]
            await channel.send(random.choice(satirical_messages))
            await self.bot.log("Heist abgebrochen — keine Teilnehmer.", "WARNING")
            return

        success = random.random() < 0.4
        if success:
            total_payout = self.bank_balance + total_bet
            await channel.send(f"🎉 **JACKPOT! DER ÜBERFALL WAR ERFOLGREICH!** 🎉\nDie Crew erbeutet **{total_payout} Coins**!")
            self.bank_balance = 0
        else:
            await channel.send("🚨 **POLIZEI! ALLE WURDEN GESCHNAPPT!** 💥\nEingesetzte Coins sind verloren!")
            self.bank_balance += total_bet

        self.heist_participants = {}

async def setup(bot):
    await bot.add_cog(PrimeEconomyCog(bot))
    await bot.log("PrimeEconomyCog geladen.", "SUCCESS")