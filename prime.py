import discord
import os

# Token deines Bots. Es ist am besten, dies als Umgebungsvariable zu speichern.
# Für den Anfang kannst du es hier direkt einfügen, aber für die Produktion
# solltest du es sicher speichern (z.B. mit python-dotenv).
TOKEN = 'MTQxNDIxNzE3ODQxNjE1MjYxNw.GYk5it.XvUlJhBYsiEniJtDPte_cYQvRjWKlSR9PwUSFQ' # Ersetze dies durch dein kopiertes Token

intents = discord.Intents.default()
intents.message_content = True # Erforderlich, um Nachrichteninhalt lesen zu können

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot ist eingeloggt als {client.user}')
    print('------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$hallo'):
        await message.channel.send('Hallo zurück!')

    if message.content.startswith('$info'):
        await message.channel.send(f'Ich bin {client.user.name}, dein Bot-Freund!')

client.run(TOKEN)