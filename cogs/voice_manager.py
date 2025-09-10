# cogs/voice_manager.py
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

class VoiceManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_channel_id = int(bot.TEMP_CHANNEL_ID)
        self.temporary_channels = {}

    def log(self, message: str):
        asyncio.create_task(self.bot.log(f"[VOICE] {message}", "INFO"))

    async def delete_channel_if_empty(self, channel):
        await asyncio.sleep(60)
        if channel.id in self.temporary_channels and len(channel.members) == 0:
            await channel.delete()
            self.log(f"Kanal '{channel.name}' ({channel.id}) gelöscht nach 60 Sekunden Leerlauf")
            del self.temporary_channels[channel.id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id == self.temp_channel_id:
            guild = after.channel.guild
            category = after.channel.category
            
            overwrite = discord.PermissionOverwrite(
                manage_channels=True, manage_roles=True, view_channel=True,
                connect=True, speak=True, stream=True, use_voice_activation=True,
                priority_speaker=True, mute_members=True, deafen_members=True, move_members=True
            )

            temp_channel = await guild.create_voice_channel(
                name=f"{member.display_name}",
                category=category,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
                    member: overwrite
                }
            )
            
            temp_channel_base = guild.get_channel(self.temp_channel_id)
            if temp_channel_base:
                new_position = temp_channel_base.position + 1
                await temp_channel.edit(position=new_position)
                self.log(f"Kanal '{temp_channel.name}' erstellt unter '{temp_channel_base.name}'")

            await member.move_to(temp_channel)
            self.log(f"{member.display_name} in '{temp_channel.name}' verschoben")
            self.temporary_channels[temp_channel.id] = temp_channel

        if before.channel and before.channel.id in self.temporary_channels:
            channel_to_check = self.bot.get_channel(before.channel.id)
            if channel_to_check and len(channel_to_check.members) == 0:
                asyncio.create_task(self.delete_channel_if_empty(channel_to_check))

async def setup(bot):
    await bot.add_cog(VoiceManagerCog(bot))
    await bot.log("VoiceManagerCog geladen.", "SUCCESS")