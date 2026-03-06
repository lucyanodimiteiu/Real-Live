
import os
import asyncio
from telethon import TelegramClient

# Citim datele din GitHub Secrets (setate anterior)
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA')

async def main():
    # Folosim session_name pentru a evita conflictele de sesiune
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"Bot-ul a pornit cu succes sub sesiunea: {session_name}")
    
    # Aici adaugi logica ta de postat știri (Stiri)
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    # Menține bot-ul activ
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
