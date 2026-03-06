import os
import asyncio
from telethon import TelegramClient

# Preluam variabilele folosind numele corectate
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA_ID') # Aici am adaugat _ID

async def main():
    # Verificare rapida
    if not all([api_id, api_hash, bot_token, session_name]):
        print("EROARE: Unul dintre secrete lipseste!")
        print(f"Status: API_ID:{'OK' if api_id else 'LIPSA'}, SESSION:{'OK' if session_name else 'LIPSA'}")
        return

    # Pornim clientul
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"SUCCES! Bot-ul a pornit cu sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
