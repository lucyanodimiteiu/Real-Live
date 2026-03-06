import os
import asyncio
from telethon import TelegramClient

# Citim datele din GitHub Secrets
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA')

async def main():
    # Verificăm dacă toate secretele sunt prezente
    if not all([api_id, api_hash, bot_token, session_name]):
        print("Eroare: Lipsesc secretele din setările GitHub!")
        return

    # Inițializăm clientul NEXTALIVEROMANIA
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"Bot-ul a pornit cu succes sub sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    # Menține bot-ul activ
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
