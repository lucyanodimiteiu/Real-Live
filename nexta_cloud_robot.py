import os
import asyncio
import re
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession

# Configurații GitHub Secrets
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')

# Această linie este "plasa de siguranță":
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY') or ""

# Canale Sursă OSINT & Militare
CANALE_SURSA = [
    'nexta_live',
    'TheStudyofWar',
    'osintdefender',
    'mossad_telegram',
    'MossadPersian',
    'mossadinfarsi'
]
SEMNATURA_NOASTRA = '@real_live_by_Luci'

async def genereaza_rezumat_ai(text_original):
    """Folosește stilul premium din script.py pentru a rescrie știrea"""
    if not DEEPSEEK_KEY:
        return text_original
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Ești un jurnalist de elită, expert în analiză militară și OSINT. 
Tradu și rescrie textul de mai jos într-un stil impecabil, șlefuit și autoritar.

REGULI:
1. FĂRĂ NUMEROTARE: Nu folosi cifre (1, 2, 3) sau bullet-uri. Textul trebuie să fie un flux narativ.
2. TON: Profesional, analitic și sobru.
3. DATE: Păstrează cifrele, locațiile și orele exacte.
4. LIMBA: Română corectă și jurnalistică.

ȘTIREA: {text_original}

REDACTEAZĂ DOAR TEXTUL FINAL.
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4
        }, headers=headers, timeout=60).json()
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Eroare DeepSeek: {e}")
        return text_original

async def proceseaza_canal(client, canal_sursa, canal_destinatie, texte_vechi):
    print(f"📡 Procesăm: @{canal_sursa}...")
    try:
        messages = await client.get_messages(canal_sursa, limit=2)
        for msg in reversed(messages):
            if not msg.text or len(msg.text) < 10:
                continue

            # Rezumat AI Premium
            text_final_ai = await genereaza_rezumat_ai(msg.text)
            
            # Verificăm duplicat (logica simplificată din script.py)
            if any(text_final_ai[:50] in (tv or "") for tv in texte_vechi):
                continue

            # Trimitem postarea
            await client.send_message(
                canal_destinatie, 
                message=f"{text_final_ai}\n\n{SEMNATURA_NOASTRA}", 
                file=msg.media
            )
            print(f"✅ Postat premium de la @{canal_sursa}")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"❌ Eroare la @{canal_sursa}: {e}")

async def main():
    if not all([api_id, api_hash, session_string, DEEPSEEK_KEY]):
        print("EROARE: Lipsesc secretele!")
        return

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    istoric = await client.get_messages(canal_destinatie_raw, limit=10)
    texte_vechi = [m.text for m in istoric if m.text]

    for sursa in CANALE_SURSA:
        await proceseaza_canal(client, sursa, canal_destinatie_raw, texte_vechi)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
