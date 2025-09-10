# cogs/roulette_game.py
import discord
from discord.ext import commands
import aiosqlite
import random

class RouletteGameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_channel_id = self.bot.config["channels"]["roulette"]

    def check_channel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure(f"❌ Dieser Befehl ist nur im <#{self.allowed_channel_id}> erlaubt!")
        return True

    @commands.group(name="roulette", invoke_without_command=True)
    async def roulette(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            await ctx.send(f"ℹ️ Nur im <#{self.allowed_channel_id}> verfügbar!")
            return
        await ctx.send("Verwende `.roulette bet <einsatz> <wette>`\nMögliche Wetten: Zahl (1-36), 'rot', 'schwarz', 'gerade', 'ungerade'")

    @roulette.command(name="bet")
    async def roulette_bet(self, ctx, bet: int, wager: str):
        self.check_channel(ctx)
        if bet <= 0:
            await ctx.send("❌ Der Einsatz muss mindestens 1 Coin betragen!")
            return

        async with aiosqlite.connect("economy.db") as db:
            cursor = await db.execute("SELECT balance FROM coins WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            balance = row[0] if row else 0

            if balance < bet:
                await ctx.send("❌ Du hast nicht genug Coins!")
                return

            await db.execute("UPDATE coins SET balance = balance - ? WHERE user_id = ?", (bet, ctx.author.id))
            await db.commit()

        number = random.randint(0, 36)
        color = "grün" if number == 0 else "rot" if number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36] else "schwarz"
        parity = "gerade" if number % 2 == 0 and number != 0 else "ungerade"

        payout = 0
        wager = wager.lower()

        if wager.isdigit():
            if int(wager) == number:
                payout = bet * 35
        elif wager == color:
            payout = bet * 2
        elif wager == parity and number != 0:
            payout = bet * 2

        embed = discord.Embed(title="🎯 PRIME ROULETTE", color=0x228B22)
        embed.add_field(name="Gedreht wurde", value=f"**{number}** ({color})", inline=False)
        embed.add_field(name="Deine Wette", value=f"**{wager}**", inline=False)

        if payout > 0:
            async with aiosqlite.connect("economy.db") as db:
                await db.execute(
                    "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                    (ctx.author.id, payout, payout)
                )
                await db.commit()
            embed.add_field(name="🎉 GEWINN!", value=f"**+{payout} Coins**", inline=False)
            embed.color = 0x00FF00
            await self.bot.log(f"{ctx.author} hat {payout} Coins im Roulette gewonnen (Einsatz: {bet}).", "SUCCESS")
        else:
            embed.add_field(name="😞 VERLOREN", value="Versuch es beim nächsten Mal!", inline=False)
            embed.color = 0xFF0000
            await self.bot.log(f"{ctx.author} hat {bet} Coins im Roulette verloren.", "INFO")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RouletteGameCog(bot))
    await bot.log("RouletteGameCog geladen.", "SUCCESS")