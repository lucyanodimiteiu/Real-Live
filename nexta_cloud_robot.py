import os
import asyncio
from telethon import TelegramClient

api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA')

async def main():
    print("--- RAPORT SECRETE GITHUB ---")
    print(f"API_ID: {'✅ PREZENT' if api_id else '❌ LIPSA'}")
    print(f"API_HASH: {'✅ PREZENT' if api_hash else '❌ LIPSA'}")
    print(f"NEW_NEXTA_BOT: {'✅ PREZENT' if bot_token else '❌ LIPSA'}")
    print(f"NEXTALIVEROMANIA: {'✅ PREZENT' if session_name else '❌ LIPSA'}")
    print("-----------------------------")

    if not api_id or not api_hash or not bot_token or not session_name:
        print("Eroare: Scriptul se opreste pentru ca lipseste un secret de mai sus.")
        return

    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"SUCCES! Bot-ul a pornit cu sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
