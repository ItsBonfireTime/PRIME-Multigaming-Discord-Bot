# cogs/voice_manager.py
import discord
from discord.ext import commands
from datetime import datetime
import asyncio

class VoiceManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Lese TEMP_CHANNEL_ID aus Umgebungsvariable — optional erweiterbar pro Server später
        self.temp_channel_id = int(bot.TEMP_CHANNEL_ID)
        self.temporary_channels = {}  # {channel_id: channel_object}

    def log(self, message: str):
        """Interne Log-Funktion mit Zeitstempel"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] [VOICE] {message}")

    async def delete_channel_if_empty(self, channel):
        """Löscht einen Kanal, wenn er 60 Sekunden lang leer ist"""
        await asyncio.sleep(60)
        if channel.id in self.temporary_channels and len(channel.members) == 0:
            await channel.delete()
            self.log(f"Temporärer Kanal '{channel.name}' ({channel.id}) gelöscht nach 60 Sekunden Leerlauf")
            del self.temporary_channels[channel.id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Erstellt temporäre Sprachkanäle, wenn jemand den Trigger-Kanal betritt"""
        
        # Mitglied ist dem TEMP_CHANNEL_ID beigetreten
        if after.channel and after.channel.id == self.temp_channel_id:
            guild = after.channel.guild
            category = after.channel.category
            
            # Berechtigungen für den Ersteller
            overwrite = discord.PermissionOverwrite(
                manage_channels=True,
                manage_roles=True,
                manage_webhooks=True,
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                priority_speaker=True,
                mute_members=True,
                deafen_members=True,
                move_members=True
            )

            # Erstelle neuen Sprachkanal
            temp_channel = await guild.create_voice_channel(
                name=f"{member.display_name}",
                category=category,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
                    member: overwrite
                }
            )
            
            # Setze Position direkt unter TEMP_CHANNEL
            temp_channel_base = guild.get_channel(self.temp_channel_id)
            if temp_channel_base:
                new_position = temp_channel_base.position + 1
                await temp_channel.edit(position=new_position)
                self.log(f"Kanal '{temp_channel.name}' ({temp_channel.id}) erstellt unter '{temp_channel_base.name}'")

            # Mitglied verschieben
            await member.move_to(temp_channel)
            self.log(f"{member.display_name} in '{temp_channel.name}' verschoben")
            self.temporary_channels[temp_channel.id] = temp_channel

        # Überprüfen, ob ein temporärer Kanal gelöscht werden muss
        if before.channel and before.channel.id in self.temporary_channels:
            channel_to_check = self.bot.get_channel(before.channel.id)
            if channel_to_check and len(channel_to_check.members) == 0:
                asyncio.create_task(self.delete_channel_if_empty(channel_to_check))

async def setup(bot):
    # Stelle sicher, dass TEMP_CHANNEL_ID gesetzt ist
    if not hasattr(bot, 'TEMP_CHANNEL_ID'):
        raise RuntimeError("❌ TEMP_CHANNEL_ID muss in der Hauptdatei als bot.TEMP_CHANNEL_ID gesetzt sein!")
    
    await bot.add_cog(VoiceManagerCog(bot))
    print("[COGS] VoiceManagerCog erfolgreich geladen.")