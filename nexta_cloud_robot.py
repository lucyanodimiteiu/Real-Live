import os
import asyncio
from telethon import TelegramClient
from googletrans import Translator

# Configurare din Secretele GitHub
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['NEW_NEXTA_BOT']
CHANNEL_ID = int(os.environ['NEXTALIVEROMA'])

async def main():
    client = TelegramClient('bot_session', API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)
    translator = Translator()

    print("📡 Verific Nexta Live...")
    async for message in client.iter_messages('nexta_live', limit=1):
        if message.text:
            print(f"📝 Traduc textul...")
            translation = translator.translate(message.text, dest='ro')
            text_final = f"{translation.text}\n\nSursă: @nexta_live"
            
            if message.media:
                await client.send_file(CHANNEL_ID, message.media, caption=text_final)
            else:
                await client.send_message(CHANNEL_ID, text_final)
            print("✅ Postat cu succes!")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
