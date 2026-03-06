import os
import asyncio
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator

# Configurații preluate din Secretele GitHub
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')

CANAL_SURSA = 'nexta_live'
SEMNATURA_NOASTRA = '@real_live' # Semnătura ta

def curata_textul(text):
    """Elimină tag-urile sursei originale"""
    unwanted = [
        '@nexta_live', 
        'nexta_live', 
        't.me/nexta_live', 
        't.status/nexta_live',
        't.me/nexta_tv',
        '@nexta_tv'
    ]
    
    for word in unwanted:
        text = text.replace(word, "")
    
    # Eliminăm orice link de tip t.me către sursă
    text = re.sub(r'https?://t\.me/nexta\S+', '', text)
    
    return text.strip()

async def main():
    if not api_id or not api_hash or not session_string or not canal_destinatie_raw:
        print("EROARE: Lipsesc secretele din GitHub!")
        return

    # Validare ID Canal
    try:
        if str(canal_destinatie_raw).startswith('-100') or str(canal_destinatie_raw).isdigit():
            canal_destinatie = int(canal_destinatie_raw)
        else:
            canal_destinatie = canal_destinatie_raw
    except:
        canal_destinatie = canal_destinatie_raw

    print("Conectare la Telegram...")
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("EROARE: Sesiunea este invalidă.")
        return
        
    print(f"Extragere știri de pe {CANAL_SURSA}...")
    try:
        messages = await client.get_messages(CANAL_SURSA, limit=2)
        translator = GoogleTranslator(source='auto', target='ro')

        for msg in reversed(messages):
            if msg.text and len(msg.text) > 2:
                print("Procesare text (traducere + curățare + semnătură)...")
                text_tradus = translator.translate(msg.text)
                
                # Curățăm textul de sursa veche
                text_curat = curata_textul(text_tradus)
                
                # Adăugăm semnătura @real_live la final
                text_final = f"{text_curat}\n\n{SEMNATURA_NOASTRA}"
                
                # Trimitere pe canalul tău
                await client.send_message(canal_destinatie, message=text_final, file=msg.media)
                print(f"✅ Știre postată cu semnătura {SEMNATURA_NOASTRA}!")
                
                await asyncio.sleep(5)
            else:
                print("Mesaj fără text, sărit.")

    except Exception as e:
        print(f"❌ Eroare: {e}")

    print("Misiune îndeplinită.")

if __name__ == '__main__':
    asyncio.run(main())
