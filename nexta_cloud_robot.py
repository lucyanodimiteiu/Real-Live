import os
import asyncio
from telethon import TelegramClient
from deep_translator import GoogleTranslator

api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('NEW_NEXTA_BOT')
session_name = os.getenv('NEXTALIVEROMANIA_ID')

# Setăm sursa și destinația
CANAL_SURSA = 'nexta_live'
CANAL_DESTINATIE = '@NextaLiveRomania' # Asigură-te că botul tău e admin aici

async def main():
    if not api_id or not api_hash or not bot_token or not session_name:
        print("EROARE: Lipsesc secrete din GitHub!")
        return

    # Conectare bot
    client = TelegramClient(session_name, int(api_id), api_hash)
    await client.start(bot_token=bot_token)
    print("Conexiune stabilită cu succes. Începem procesul...")

    try:
        print(f"Extragem ultimele știri de pe {CANAL_SURSA}...")
        # Luăm ultimele 2 mesaje de pe canalul sursă
        messages = await client.get_messages(CANAL_SURSA, limit=2)
        
        translator = GoogleTranslator(source='auto', target='ro')

        # Le luăm în ordine inversă (cea mai veche prima)
        for msg in reversed(messages):
            if msg.text:
                # Traducem textul
                text_tradus = translator.translate(msg.text)
                
                # Postăm pe canalul tău (text + media, dacă există)
                await client.send_message(CANAL_DESTINATIE, text=text_tradus, file=msg.media)
                print("✅ Știre tradusă și postată cu succes pe canalul tău!")
                
                # Pauză între postări pentru a nu fi blocați de Telegram
                await asyncio.sleep(5)
            else:
                print("Mesajul nu conține text, îl sărim deocamdată.")

    except Exception as e:
        print(f"❌ A apărut o eroare: {e}")
        print("Dacă eroarea spune 'ChannelPrivateError', înseamnă că API-ul Telegram nu lasă botul să citească dintr-un canal public unde nu e admin. Vom schimba metoda de autentificare.")

    print("Proces finalizat. Botul se oprește.")

if __name__ == '__main__':
    asyncio.run(main())
