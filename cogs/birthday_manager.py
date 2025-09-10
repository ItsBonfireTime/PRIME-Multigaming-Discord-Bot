# cogs/birthday_manager.py
import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import asyncio
import aiosqlite

class BirthdayManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_channel_id = self.bot.config["channels"]["birthday"]
        self.birthday_role_id = self.bot.config["roles"]["birthday"]
        self.birthdays_file = "birthdays.json"
        self.milestone_ages = {18, 21, 30, 40, 50, 60, 70, 80, 90, 100}
        self.ensure_file_exists()

    def ensure_file_exists(self):
        if not os.path.exists(self.birthdays_file):
            with open(self.birthdays_file, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)
            asyncio.create_task(self.bot.log("birthdays.json erstellt.", "INFO"))

    def load_birthdays(self):
        with open(self.birthdays_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_birthdays(self, data):
        with open(self.birthdays_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def check_channel(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            raise commands.CheckFailure(f"❌ Dieser Befehl ist nur im <#{self.allowed_channel_id}> erlaubt!")
        return True

    @commands.group(name="birthday", invoke_without_command=True)
    async def birthday(self, ctx):
        if ctx.channel.id != self.allowed_channel_id:
            await ctx.send(f"ℹ️ Nur im <#{self.allowed_channel_id}> verfügbar!")
            return
        await ctx.send("Verwende `.birthday set <DD.MM.JJJJ>`, `.birthday me` oder `.birthday list`")

    @birthday.command(name="set")
    async def birthday_set(self, ctx, date_str: str):
        self.check_channel(ctx)
        try:
            parts = date_str.split(".")
            if len(parts) != 3:
                raise ValueError
            day, month, year = map(int, parts)
            birth_date = datetime(year=year, month=month, day=day)
            if birth_date > datetime.utcnow():
                raise ValueError("Geburtsdatum liegt in der Zukunft!")
        except (ValueError, IndexError):
            await ctx.send("❌ Ungültiges Format! Verwende `DD.MM.JJJJ` (z. B. `24.12.1995`)")
            return

        birthdays = self.load_birthdays()
        birthdays[str(ctx.author.id)] = {
            "name": ctx.author.display_name,
            "date": f"{day:02d}.{month:02d}.{year:04d}"
        }
        self.save_birthdays(birthdays)

        await ctx.send(f"✅ {ctx.author.mention}, dein Geburtstag **{day:02d}.{month:02d}.{year:04d}** wurde gespeichert!")
        await self.bot.log(f"{ctx.author} hat Geburtstag auf {day:02d}.{month:02d}.{year:04d} gesetzt.", "INFO")

    @birthday.command(name="me")
    async def birthday_me(self, ctx):
        self.check_channel(ctx)
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if user_id not in birthdays:
            await ctx.send("❌ Du hast noch keinen Geburtstag eingetragen!")
            return

        bday_str = birthdays[user_id]["date"]
        day, month, year = map(int, bday_str.split("."))
        today = datetime.utcnow().date()
        birth_date = datetime(year=year, month=month, day=day).date()
        age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        this_year_bday = today.replace(year=today.year, month=month, day=day)
        next_bday = this_year_bday if this_year_bday >= today else today.replace(year=today.year + 1, month=month, day=day)
        days_left = (next_bday - today).days

        if days_left == 0:
            await ctx.send(f"🎉 HEUTE IST DEIN GEBURTSTAG, {ctx.author.mention}! 🎂 Alles Gute!\n Du bist jetzt **{age} Jahre** alt!")
        else:
            await ctx.send(f"🎂 Dein Geburtstag ist am **{bday_str}** — noch **{days_left} Tage** bis zum nächsten!\n Du bist **{age} Jahre** alt.")

    @birthday.command(name="list")
    async def birthday_list(self, ctx):
        self.check_channel(ctx)
        birthdays = self.load_birthdays()
        if not birthdays:
            await ctx.send("ℹ️ Noch keine Geburtstage eingetragen.")
            return

        sorted_birthdays = sorted(
            birthdays.items(),
            key=lambda x: (int(x[1]["date"].split(".")[1]), int(x[1]["date"].split(".")[0]))
        )

        embed = discord.Embed(title="🎂 Geburtstagskalender", color=0xFF69B4)
        for user_id, data in sorted_birthdays:
            user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
            name = user.display_name if user else data["name"]
            embed.add_field(name=data["date"], value=name, inline=True)

        await ctx.send(embed=embed)

    @tasks.loop(minutes=1)
    async def weekly_birthday_preview(self):
        now = datetime.utcnow()
        if now.weekday() == 0 and now.hour == 8 and now.minute == 0:
            today = now.date()
            week_end = today + timedelta(days=6)
            birthdays = self.load_birthdays()
            upcoming = []

            for user_id_str, data in birthdays.items():
                day, month, year = map(int, data["date"].split("."))
                this_year_bday = today.replace(month=month, day=day)
                next_bday = this_year_bday if this_year_bday >= today else today.replace(year=today.year + 1, month=month, day=day)
                if today <= next_bday <= week_end:
                    user = self.bot.get_user(int(user_id_str)) or await self.bot.fetch_user(int(user_id_str))
                    name = user.display_name if user else data["name"]
                    upcoming.append((next_bday, name, data["date"], user_id_str))

            upcoming.sort(key=lambda x: x[0])
            channel = self.bot.get_channel(self.allowed_channel_id)
            if not channel:
                return

            if not upcoming:
                await channel.send("ℹ️ **Diese Woche hat niemand Geburtstag.** 🎂")
                return

            embed = discord.Embed(
                title="📅 Geburtstage diese Woche",
                color=0xFF69B4,
                description="Notiere dir die Termine — lass uns gemeinsam feiern! 🎉"
            )
            for date_obj, name, date_str, user_id in upcoming:
                days_until = (date_obj - today).days
                when = "🎉 HEUTE!" if days_until == 0 else f"in {days_until} Tagen"
                embed.add_field(name=f"{date_str} — {name}", value=when, inline=False)

            await channel.send(embed=embed)
            await self.bot.log("Wöchentliche Geburtstagsvorschau gepostet.", "INFO")

    @tasks.loop(minutes=1)
    async def check_birthday_actions(self):
        now = datetime.utcnow()
        birthdays = self.load_birthdays()

        if now.hour == 8 and now.minute == 0:
            today_str = f"{now.day:02d}.{now.month:02d}"
            celebrants = []

            for user_id_str, data in birthdays.items():
                bday_parts = data["date"].split(".")
                bday_day_month = f"{bday_parts[0]}.{bday_parts[1]}"
                if bday_day_month == today_str:
                    user_id = int(user_id_str)
                    for guild in self.bot.guilds:
                        member = guild.get_member(user_id)
                        if member:
                            day, month, year = map(int, data["date"].split("."))
                            birth_date = datetime(year=year, month=month, day=day).date()
                            today = now.date()
                            age = today.year - birth_date.year
                            if (today.month, today.day) < (birth_date.month, birth_date.day):
                                age -= 1

                            coins_to_give = 200
                            if age in self.milestone_ages:
                                coins_to_give += 500
                                await self.bot.log(f"{member.display_name} erhält Bonus-Coins für {age}. Geburtstag!", "SUCCESS")

                            try:
                                async with aiosqlite.connect("economy.db") as db:
                                    await db.execute(
                                        "INSERT INTO coins (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                                        (user_id, coins_to_give, coins_to_give)
                                    )
                                    await db.commit()
                            except Exception as e:
                                await self.bot.log(f"Fehler beim Coins-Gutschreiben für {member.display_name}: {e}", "ERROR")

                            role = guild.get_role(self.birthday_role_id)
                            if role and role not in member.roles:
                                try:
                                    await member.add_roles(role)
                                except discord.Forbidden:
                                    await self.bot.log(f"Keine Rechte, Rolle in {guild.name} zu vergeben.", "ERROR")
                            celebrants.append((member, age, coins_to_give))

            if celebrants:
                channel = self.bot.get_channel(self.allowed_channel_id)
                if channel:
                    messages = []
                    for member, age, coins in celebrants:
                        msg = f"🎉 **ALLES GUTE ZUM {age}. GEBURTSTAG, {member.mention}!** 🎂\n🎁 **+{coins} Coins** wurden dir gutgeschrieben!\n👑 Du hast die **Geburtstags-Rolle** erhalten!"
                        messages.append(msg)
                    await channel.send("\n\n".join(messages))
                    await self.bot.log(f"Gratulation an {len(celebrants)} User gesendet.", "SUCCESS")

        elif now.hour == 23 and now.minute == 59:
            for guild in self.bot.guilds:
                role = guild.get_role(self.birthday_role_id)
                if not role:
                    continue
                for member in role.members:
                    try:
                        await member.remove_roles(role)
                    except discord.Forbidden:
                        await self.bot.log(f"Keine Rechte, Rolle von {member.display_name} in {guild.name} zu entfernen.", "ERROR")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        user_id = str(member.id)
        birthdays = self.load_birthdays()
        if user_id in birthdays:
            del birthdays[user_id]
            self.save_birthdays(birthdays)
            await self.bot.log(f"{member.display_name} ({member.id}) aus birthdays.json entfernt (Server verlassen).", "INFO")

    @weekly_birthday_preview.before_loop
    async def before_weekly_birthday_preview(self):
        await self.bot.wait_until_ready()

    @check_birthday_actions.before_loop
    async def before_check_birthday_actions(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        self.weekly_birthday_preview.start()
        self.check_birthday_actions.start()
        await self.bot.log("BirthdayManagerCog geladen.", "SUCCESS")

    async def cog_unload(self):
        self.weekly_birthday_preview.cancel()
        self.check_birthday_actions.cancel()

async def setup(bot):
    await bot.add_cog(BirthdayManagerCog(bot))