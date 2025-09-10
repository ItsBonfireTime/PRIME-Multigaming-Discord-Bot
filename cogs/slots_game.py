# cogs/slots_game.py
import discord
from discord.ext import commands
import aiosqlite
import random

class SlotsGameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_channel_id = self.bot.config["channels"]["slots"]

    def check_channel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure(f"❌ Dieser Befehl ist nur im <#{self.allowed_channel_id}> erlaubt!")
        return True

    @commands.group(name="slots", invoke_without_command=True)
    async def slots(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            await ctx.send(f"ℹ️ Nur im <#{self.allowed_channel_id}> verfügbar!")
            return
        await ctx.send("Verwende `.slots play <einsatz>`")

    @slots.command(name="play")
    async def slots_play(self, ctx, bet: int):
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

        symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
        spin = [random.choice(symbols) for _ in range(3)]
        result = " | ".join(spin)

        payout = 0
        if spin[0] == spin[1] == spin[2]:
            if spin[0] == "7️⃣":
                payout = bet * 10
            elif spin[0] == "💎":
                payout = bet * 5
            else:
                payout = bet * 3
        elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
            payout = bet * 2

        embed = discord.Embed(title="🎰 PRIME SLOTS", color=0x8A2BE2)
        embed.add_field(name="Dein Einsatz", value=f"**{bet}** Coins", inline=False)
        embed.add_field(name="Walzen", value=f"**{result}**", inline=False)

        if payout > 0:
            async with aiosqlite.connect("economy.db") as db:
                await db.execute(
                    "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                    (ctx.author.id, payout, payout)
                )
                await db.commit()
            embed.add_field(name="🎉 GEWINN!", value=f"**+{payout} Coins**", inline=False)
            embed.color = 0x00FF00
            await self.bot.log(f"{ctx.author} hat {payout} Coins im Slots gewonnen (Einsatz: {bet}).", "SUCCESS")
        else:
            embed.add_field(name="😞 VERLOREN", value="Versuch es beim nächsten Mal!", inline=False)
            embed.color = 0xFF0000
            await self.bot.log(f"{ctx.author} hat {bet} Coins im Slots verloren.", "INFO")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SlotsGameCog(bot))
    await bot.log("SlotsGameCog geladen.", "SUCCESS")