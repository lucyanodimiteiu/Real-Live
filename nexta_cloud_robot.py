import os
import asyncio
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==========================================
# CONFIGURAȚII GITHUB SECRETS
# ==========================================
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY')

# ==========================================
# SURSE OSINT & MILITARE
# ==========================================
CANALE_SURSA = [
    'nexta_live',
    'TheStudyofWar',
    'osintdefender',
    'mossad_telegram',
    'MossadPersian',
    'mossadinfarsi'
]
SEMNATURA_NOASTRA = '@real_live'

async def genereaza_rezumat_ai(text_original):
    if not DEEPSEEK_KEY:
        return text_original
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    prompt = f"Tradu si rescrie acest text in romana jurnalistica, pastrand cifrele si locatiile, fara liste: {text_original}"
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4
        }, headers=headers, timeout=60)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return text_original

async def proceseaza_canal(client, canal_sursa, destinatie, texte_vechi):
    print(f"📡 Scan: @{canal_sursa}...")
    try:
        messages = await client.get_messages(canal_sursa, limit=2)
        for msg in reversed(messages):
            if not msg.text or len(msg.text) < 10: continue
            text_final = await genereaza_rezumat_ai(msg.text)
            if any(text_final[:50] in (tv or "") for tv in texte_vechi): continue
            
            # Trimitem mesajul către destinația corectată
            await client.send_message(destinatie, message=f"{text_final}\n\n{SEMNATURA_NOASTRA}", file=msg.media)
            print(f"✅ Postat succes de la @{canal_sursa}")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"Error @{canal_sursa}: {e}")

async def main():
    # REPARARE LOGICĂ ID
    if not all([api_id, api_hash, session_string, DEEPSEEK_KEY]):
        print("EROARE: Lipsesc secretele!")
        return

    # Forțăm transformarea ID-ului în număr întreg (integer)
    try:
        if str(canal_destinatie_raw).startswith('-100'):
            destinatie = int(canal_destinatie_raw)
        else:
            destinatie = canal_destinatie_raw
    except:
        destinatie = canal_destinatie_raw

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    # Verificăm istoricul folosind ID-ul convertit corect
    istoric = await client.get_messages(destinatie, limit=15)
    texte_vechi = [m.text for m in istoric if m.text]
    
    for sursa in CANALE_SURSA:
        await proceseaza_canal(client, sursa, destinatie, texte_vechi)
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
