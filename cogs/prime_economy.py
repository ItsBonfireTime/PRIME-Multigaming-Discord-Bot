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
        self.heist_participants = {}  # {user_id: bet_amount}
        self.heist_end_time = None
        self.bank_balance = 1000  # Startguthaben der Bank
        self.allowed_channel_id = 1414706257654190250  # Nur hier erlaubt!

    async def cog_load(self):
        """Erstellt Datenbanktabellen beim Laden"""
        async with aiosqlite.connect("economy.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS coins (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1
                )
            """)
            await db.commit()
        print("[ECONOMY] Datenbanktabellen erstellt.")
        self.hourly_heist.start()  # Starte den automatischen Heist-Timer

    def cog_unload(self):
        self.hourly_heist.cancel()

    def check_channel(self, ctx):
        """Prüft, ob der Befehl im erlaubten Channel ausgeführt wurde"""
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure("❌ Dieser Befehl ist nur im <#1414706257654190250> erlaubt!")
        return True

    @commands.check
    async def globally_check_channel(self, ctx):
        return self.check_channel(ctx)

    @commands.group(name="prime", invoke_without_command=True)
    async def prime(self, ctx):
        """Hauptbefehl für PRIME-Bot Funktionen"""
        if ctx.channel.id != self.allowed_channel_id:
            return
        await ctx.send("Verwende `.prime convert`, `.prime bank` oder `.prime heist`")

    @prime.group(name="convert", invoke_without_command=True)
    async def prime_convert(self, ctx):
        """Wandle XP in Coins um"""
        if ctx.channel.id != self.allowed_channel_id:
            return
        await ctx.send_help(ctx.command)

    @prime_convert.command(name="xp")
async def convert_xp(self, ctx, amount: int):
    """Wandle XP in Coins um (100 XP = 1 Coin) — liest XP aus leveling.db"""
    self.check_channel(ctx)
    if amount <= 0:
        await ctx.send("❌ Du musst mehr als 0 XP umwandeln!")
        return

    # Lies XP aus leveling.db (nicht economy.db!)
    async with aiosqlite.connect("leveling.db") as db:
        cursor = await db.execute("SELECT xp FROM users WHERE user_id = ?", (ctx.author.id,))
        row = await cursor.fetchone()
        if not row or row[0] < amount:
            await ctx.send("❌ Du hast nicht genug XP!")
            return

        coins = amount // 100
        if coins == 0:
            await ctx.send("❌ Du brauchst mindestens 100 XP für 1 Coin!")
            return

        # XP abbuchen in leveling.db
        await db.execute("UPDATE users SET xp = xp - ? WHERE user_id = ?", (amount, ctx.author.id))
        await db.commit()

    # Coins gutschreiben in economy.db
    async with aiosqlite.connect("economy.db") as db:
        await db.execute(
            "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
            (ctx.author.id, coins, coins)
        )
        await db.commit()

    await ctx.send(f"✅ Du hast **{amount} XP** in **{coins} Coins** umgewandelt!")

    @prime.group(name="bank", invoke_without_command=True)
    async def prime_bank(self, ctx):
        """Zeige Bank-Infos"""
        if ctx.channel.id != self.allowed_channel_id:
            return
        await ctx.send_help(ctx.command)

    @prime_bank.command(name="balance")
    async def bank_balance(self, ctx, member: discord.Member = None):
        """Zeige dein Coin-Guthaben — NUR im Economy-Channel"""
        self.check_channel(ctx)
        member = member or ctx.author
        async with aiosqlite.connect("economy.db") as db:
            cursor = await db.execute("SELECT balance FROM coins WHERE user_id = ?", (member.id,))
            row = await cursor.fetchone()
            balance = row[0] if row else 0

            embed = discord.Embed(
                title=f"💰 Bankkonto von {member.display_name}",
                color=0xF1C40F
            )
            embed.add_field(name="Coins", value=f"**{balance}**", inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            await ctx.send(embed=embed)

    @prime.group(name="heist", invoke_without_command=True)
    async def prime_heist(self, ctx):
        """Starte oder joine einen Banküberfall"""
        if ctx.channel.id != self.allowed_channel_id:
            return
        await ctx.send_help(ctx.command)

    @prime_heist.command(name="join")
    async def heist_join(self, ctx, amount: int):
        """Nimm am laufenden Überfall teil — NUR im Economy-Channel"""
        self.check_channel(ctx)
        if not self.heist_active:
            await ctx.send("❌ Es läuft kein Überfall!")
            return

        if amount <= 0:
            await ctx.send("❌ Du musst mehr als 0 Coins setzen!")
            return

        async with aiosqlite.connect("economy.db") as db:
            cursor = await db.execute("SELECT balance FROM coins WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            balance = row[0] if row else 0

            if balance < amount:
                await ctx.send("❌ Du hast nicht genug Coins!")
                return

            await db.execute("UPDATE coins SET balance = balance - ? WHERE user_id = ?", (amount, ctx.author.id))
            await db.commit()

        self.heist_participants[ctx.author.id] = amount
        await ctx.send(f"✅ {ctx.author.mention} hat **{amount} Coins** in den Überfall investiert!")

    @tasks.loop(minutes=1)
    async def hourly_heist(self):
        """Startet automatisch einen Heist zu jeder vollen Stunde"""
        now = datetime.utcnow()
        if now.minute == 0:  # Volle Stunde
            channel = self.bot.get_channel(self.allowed_channel_id)
            if not channel:
                print("[ECONOMY] Economy-Channel nicht gefunden!")
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
                f"⏱️ Du hast **10 Minuten**, um mit `.prime heist join <amount>` teilzunehmen!\n"
                f"🎯 Erfolgschance: 40% — bei Erfolg wird die Beute geteilt, bei Misserfolg verlierst du alles!"
            )

            await asyncio.sleep(600)  # 10 Minuten warten
            await self.resolve_heist(channel)

    @hourly_heist.before_loop
    async def before_hourly_heist(self):
        await self.bot.wait_until_ready()
        # Warte bis zur nächsten vollen Stunde
        now = datetime.utcnow()
        sleep_seconds = (60 - now.minute) * 60 - now.second
        await asyncio.sleep(sleep_seconds)

    async def resolve_heist(self, channel):
        if not self.heist_active:
            return

        self.heist_active = False
        total_bet = sum(self.heist_participants.values())

        if total_bet == 0:
            # 🤡 SATIRISCHE NACHRICHT — KEINER HAT TEILGENOMMEN
            satirical_messages = [
                "🕵️‍♂️ *Die Bankräuber kamen mit Taschenlampen und Strumpfmasken... aber niemand war da. Die Kasse lachte sie aus.*",
                "🏦 *Die PRIME-Bank schickte eine Rechnung für 'versuchten Überfall'. Bezahlbar in Seufzern.*",
                "🦹‍♂️ *Der Meisterdieb flüsterte: 'Wo ist die Crew?' — Stille. Nicht mal eine Taube kam zum Raub.*",
                "💸 *Die Banknoten feierten Party — ohne Gäste. Sie tanzten allein unter den Überwachungskameras.*",
                "👮 *Die Polizei kam, sah niemanden, und verhaftete eine Schnecke. Sie gestand alles.*"
            ]
            await channel.send(random.choice(satirical_messages))
            return

        success = random.random() < 0.4  # 40% Chance

        if success:
            total_payout = self.bank_balance + total_bet
            await channel.send(f"🎉 **JACKPOT! DER ÜBERFALL WAR ERFOLGREICH!** 🎉\nDie Crew erbeutet **{total_payout} Coins**!")

            # 🎉 LUSTIGE GEWINNER-NACHRICHT MIT @USER
            winner_messages = [
                "👑 {user} klaut die Show — und die Kasse!",
                "🤑 {user} hat den Tresor geknackt — mit einem Gummihuhn!",
                "🕶️ {user} verschwindet im Rauch — mit dem Geldkoffer!",
                "🦹‍♀️ {user} lacht: 'Wer braucht schon einen Plan?' — und gewinnt alles!",
                "🎭 {user} verkleidet sich als Bankmanager — und räumt ab!"
            ]

            async with aiosqlite.connect("economy.db") as db:
                for user_id, bet in self.heist_participants.items():
                    share = int((bet / total_bet) * total_payout)
                    await db.execute(
                        "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                        (user_id, share, share)
                    )
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    msg = random.choice(winner_messages).format(user=user.mention)
                    await channel.send(f"💰 {msg} — **+{share} Coins**!")

                await db.commit()

            self.bank_balance = 0
        else:
            await channel.send("🚨 **POLIZEI! ALLE WURDEN GESCHNAPPT!** 💥\nEingesetzte Coins sind verloren — die Bank dankt für die Spende!")
            self.bank_balance += total_bet

        self.heist_participants = {}

async def setup(bot):
    await bot.add_cog(PrimeEconomyCog(bot))
    print("[COGS] PrimeEconomyCog mit automatischem Heist geladen.")