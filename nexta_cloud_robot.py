import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator

# Preluăm toate secretele din GitHub
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
# Folosim ID-ul salvat de tine în Secrets
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')

CANAL_SURSA = 'nexta_live'

async def main():
    if not api_id or not api_hash or not session_string or not canal_destinatie_raw:
        print("EROARE: Lipsesc secretele din GitHub! Verifică toate cele 4 variabile.")
        return

    # Pregătim ID-ul canalului (dacă e număr, îl convertim în întreg)
    try:
        if canal_destinatie_raw.startswith('-100') or canal_destinatie_raw.isdigit():
            canal_destinatie = int(canal_destinatie_raw)
        else:
            canal_destinatie = canal_destinatie_raw
    except:
        canal_destinatie = canal_destinatie_raw

    print("Ne conectăm la Telegram ca Utilizator...")
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("EROARE: Sesiunea a expirat sau este invalidă.")
        return
        
    print(f"Conexiune stabilă! Extragem știri de pe {CANAL_SURSA}...")
    try:
        messages = await client.get_messages(CANAL_SURSA, limit=2)
        translator = GoogleTranslator(source='auto', target='ro')

        for msg in reversed(messages):
            if msg.text:
                print("Traducem știrea...")
                text_tradus = translator.translate(msg.text)
                
                # Trimiterea mesajului folosind ID-ul numeric sigur
                await client.send_message(canal_destinatie, message=text_tradus, file=msg.media)
                print("✅ Știre postată cu succes pe canalul tău!")
                
                await asyncio.sleep(5)
            else:
                print("Sărim peste un mesaj fără text.")

    except Exception as e:
        print(f"❌ Eroare la procesare: {e}")

    print("Proces finalizat.")

if __name__ == '__main__':
    asyncio.run(main())
