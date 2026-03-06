import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator

# Preluăm secretele din GitHub
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION') 

CANAL_SURSA = 'nexta_live'
CANAL_DESTINATIE = '@NextaLiveRomania'

async def main():
    if not api_id or not api_hash or not session_string:
        print("EROARE: Lipsesc secretele din GitHub (inclusiv TELEGRAM_SESSION)!")
        return

    print("Ne conectăm la Telegram ca Utilizator...")
    # Ne conectăm direct cu sesiunea ta
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("EROARE: TELEGRAM_SESSION este invalidă.")
        return
        
    print("Conexiune stabilită! Extragem ultimele 2 știri de pe Nexta Live...")
    try:
        # Citim istoricul ca utilizator cu drepturi depline
        messages = await client.get_messages(CANAL_SURSA, limit=2)
        translator = GoogleTranslator(source='auto', target='ro')

        for msg in reversed(messages):
            if msg.text:
                text_tradus = translator.translate(msg.text)
                
                # AICI ESTE CORECTURA: am schimbat text= cu message=
                await client.send_message(CANAL_DESTINATIE, message=text_tradus, file=msg.media)
                print("✅ Știre tradusă și postată cu succes!")
                
                await asyncio.sleep(5) # Pauză scurtă între postări
            else:
                print("Mesajul nu conține text, trecem peste.")

    except Exception as e:
        print(f"❌ A apărut o eroare: {e}")

    print("Proces finalizat cu succes! Scriptul se oprește.")

if __name__ == '__main__':
    asyncio.run(main())
