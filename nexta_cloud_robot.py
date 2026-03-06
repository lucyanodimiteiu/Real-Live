import os
import asyncio
from telethon import TelegramClient

# Preluăm variabilele "injectate" de fișierul YAML de mai sus
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA')

async def main():
    # Verificăm din nou dacă au ajuns valorile
    if not all([api_id, api_hash, bot_token, session_name]):
        print(f"DEBUG - API_ID: {api_id}")
        print(f"DEBUG - API_HASH: {api_hash}")
        print("Eroare: Secretele încă nu sunt văzute de script!")
        return

    # Pornim clientul
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"SUCCES! Bot-ul a pornit sub sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
