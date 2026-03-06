import os
import asyncio
from telethon import TelegramClient, events

# Preluăm secretele din GitHub
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA_ID')

async def main():
    if not api_id or not api_hash or not bot_token or not session_name:
        print("EROARE: Lipsesc secrete din GitHub! Scriptul se oprește.")
        return

    # Inițializăm clientul
    client = TelegramClient(session_name, int(api_id), api_hash)
    
    # --- AICI SUNT INSTRUCȚIUNILE NOI ---
    # Când cineva îi scrie /start, botul va răspunde:
    @client.on(events.NewMessage(pattern='(?i)/start'))
    async def start_handler(event):
        await event.reply("Salut! Sunt Grigore 🎩. Sunt online și funcționez perfect din cloud-ul GitHub!")

    # Când cineva îi scrie /status, va confirma că e activ:
    @client.on(events.NewMessage(pattern='(?i)/status'))
    async def status_handler(event):
        await event.reply("Sistemele sunt 100% operaționale. Aștept instrucțiuni, Luci! 🚀")
    # ------------------------------------
    
    # Pornim efectiv botul
    await client.start(bot_token=bot_token)
    print(f"SUCCES! Bot-ul a pornit cu sesiunea: {session_name}")
    
    me = await client.get_me()
    print(f"Logat ca: {me.username}. Aștept mesaje pe Telegram...")
    
    # Menținem botul activ pentru a asculta mesajele de mai sus
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
