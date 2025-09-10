# cogs/duel_game.py
import discord
from discord.ext import commands
import aiosqlite
import random
import asyncio

class DuelGameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_channel_id = self.bot.config["channels"]["duel"]

    def check_channel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure(f"❌ Dieser Befehl ist nur im <#{self.allowed_channel_id}> erlaubt!")
        return True

    @commands.group(name="duel", invoke_without_command=True)
    async def duel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            await ctx.send(f"ℹ️ Nur im <#{self.allowed_channel_id}> verfügbar!")
            return
        await ctx.send("Verwende `.duel challenge @user <einsatz>`")

    @duel.command(name="challenge")
    async def duel_challenge(self, ctx, opponent: discord.Member, bet: int):
        self.check_channel(ctx)
        if opponent.bot:
            await ctx.send("❌ Du kannst nicht gegen einen Bot duellieren!")
            return
        if opponent.id == ctx.author.id:
            await ctx.send("❌ Du kannst nicht gegen dich selbst spielen!")
            return
        if bet <= 0:
            await ctx.send("❌ Der Einsatz muss mindestens 1 Coin betragen!")
            return

        async with aiosqlite.connect("economy.db") as db:
            for user in [ctx.author, opponent]:
                cursor = await db.execute("SELECT balance FROM coins WHERE user_id = ?", (user.id,))
                row = await cursor.fetchone()
                balance = row[0] if row else 0
                if balance < bet:
                    await ctx.send(f"❌ {user.mention} hat nicht genug Coins!")
                    return

            for user in [ctx.author, opponent]:
                await db.execute("UPDATE coins SET balance = balance - ? WHERE user_id = ?", (bet, user.id))
            await db.commit()

        await ctx.send(f"🎲 {ctx.author.mention} fordert {opponent.mention} zu einem **Würfelduell** mit **{bet} Coins** Einsatz heraus!")
        await asyncio.sleep(3)
        await ctx.send(f"{opponent.mention}, du wurdest herausgefordert! Der Kampf beginnt...")

        player1_roll = random.randint(1, 20)
        player2_roll = random.randint(1, 20)

        embed = discord.Embed(title="🎲 WÜRFELDUELL", color=0xFF4500)
        embed.add_field(name=ctx.author.display_name, value=f"🎲 **{player1_roll}**", inline=True)
        embed.add_field(name=opponent.display_name, value=f"🎲 **{player2_roll}**", inline=True)

        winner = None
        if player1_roll > player2_roll:
            winner = ctx.author
        elif player2_roll > player1_roll:
            winner = opponent
        else:
            embed.add_field(name="⚔️ UNENTSCHIEDEN", value="Der Einsatz wird zur Hälfte zurückerstattet!", inline=False)
            async with aiosqlite.connect("economy.db") as db:
                for user in [ctx.author, opponent]:
                    refund = bet // 2
                    await db.execute(
                        "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                        (user.id, refund, refund)
                    )
                await db.commit()
            embed.color = 0xFFFF00
            await self.bot.log(f"Duell zwischen {ctx.author} und {opponent} endete unentschieden.", "INFO")
        if winner:
            total_pot = bet * 2
            embed.add_field(name="🏆 GEWINNER", value=f"{winner.mention} gewinnt **{total_pot} Coins**!", inline=False)
            async with aiosqlite.connect("economy.db") as db:
                await db.execute(
                    "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                    (winner.id, total_pot, total_pot)
                )
                await db.commit()
            embed.color = 0x00FF00
            await self.bot.log(f"{winner} hat das Duell gegen {opponent if winner == ctx.author else ctx.author} gewonnen ({total_pot} Coins).", "SUCCESS")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DuelGameCog(bot))
    await bot.log("DuelGameCog geladen.", "SUCCESS")