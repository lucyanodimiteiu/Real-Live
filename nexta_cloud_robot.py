import os
import asyncio
from telethon import TelegramClient

# Căutăm exact numele secretului pe care îl ai în GitHub
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA_ID')

async def main():
    # Raport vizual în consolă
    print("--- RAPORT SECRETE GITHUB ---")
    print(f"API_ID: {'✅ PREZENT' if api_id else '❌ LIPSA'}")
    print(f"API_HASH: {'✅ PREZENT' if api_hash else '❌ LIPSA'}")
    print(f"NEW_NEXTA_BOT: {'✅ PREZENT' if bot_token else '❌ LIPSA'}")
    print(f"NEXTALIVEROMANIA_ID: {'✅ PREZENT' if session_name else '❌ LIPSA'}")
    print("-----------------------------")

    # Oprire în caz de eroare
    if not api_id or not api_hash or not bot_token or not session_name:
        print("EROARE: Lipsesc secrete din GitHub! Verifică dacă numele coincid perfect.")
        return

    # Pornim clientul
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    await client.start(bot_token=bot_token)
    print(f"SUCCES! Bot-ul a pornit cu sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}")
    
    # Menținem botul activ
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
