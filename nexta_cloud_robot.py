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
    """
    Folosește DeepSeek pentru traducere și rescriere jurnalistică premium.
    Stil: Bloomberg/Reuters, cursiv, fără numerotare.
    """
    if not DEEPSEEK_KEY:
        return text_original
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}", 
        "Content-Type": "application/json"
    }
    
    prompt = f"""
Ești un jurnalist de elită, expert în analiză militară și OSINT. 
Tradu și rescrie textul de mai jos într-un stil impecabil, șlefuit și autoritar în limba română.

REGULI CRITICE (Stil Luci Premium):
1. FĂRĂ NUMEROTARE: Nu folosi cifre (1, 2, 3), liste cu puncte sau bullet-uri. Textul trebuie să fie un flux narativ.
2. TON: Profesional, analitic și sobru.
3. DATE: Păstrează TOATE cifrele esențiale, locațiile și orele exacte, integrându-le natural în fraze.
4. SURSĂ: Nu menționa numele canalului sursă în text.

ȘTIREA ORIGINALĂ: {text_original}

REDACTEAZĂ DOAR TEXTUL FINAL ÎN ROMÂNĂ.
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 1000
        }, headers=headers, timeout=60)
        
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"⚠️ Eroare DeepSeek: {e}")
        return None

async def proceseaza_canal(client, canal_sursa, canal_destinatie, texte_vechi):
    """Scanează mesajele noi și le trimite spre AI și apoi spre canal"""
    print(f"📡 Scanăm sursa: @{canal_sursa}...")
    try:
        # Luăm ultimele 2 mesaje pentru a evita spam-ul
        messages = await client.get_messages(canal_sursa, limit=2)
        for msg in reversed(messages):
            if not msg.text or len(msg.text) < 10:
                continue

            # 1. Generăm rezumatul cu DeepSeek
            text_final_ai = await genereaza_rezumat_ai(msg.text)
            
            if not text_final_ai:
                continue

            # 2. Verificăm dacă știrea e deja pe canal (evităm duplicatele)
            # Comparăm primele 50 de caractere
            if any(text_final_ai[:50] in (tv or "") for tv in texte_vechi):
                print(f"⏭️ Știrea de la @{canal_sursa} este deja postată. Skip.")
                continue

            # 3. Trimitem postarea (Text + Media dacă există)
            await client.send_message(
                canal_destinatie, 
                message=f"{text_final_ai}\n\n{SEMNATURA_NOASTRA}", 
                file=msg.media
            )
            print(f"✅ Postat cu succes de la @{canal_sursa}")
            
            # Pauză scurtă între postări
            await asyncio.sleep(3)
            
    except Exception as e:
        print(f"❌ Eroare la procesarea @{canal_sursa}: {e}")

async def main():
    # Verificare Secrete
    missing = []
    if not api_id: missing.append("API_ID")
    if not api_hash: missing.append("API_HASH")
    if not session_string: missing.append("TELEGRAM_SESSION")
    if not DEEPSEEK_KEY: missing.append("DEEPSEEK_API_KEY")
    if not canal_destinatie_raw: missing.append("NEXTALIVEROMANIA_ID")

    if missing:
        print(f"❌ EROARE: Lipsesc următoarele secrete în GitHub: {', '.join(missing)}")
        return

    # Conversie ID canal dacă e nevoie
    try:
        destinatie = int(canal_destinatie_raw)
    except:
        destinatie = canal_destinatie_raw

    # Pornire Client Telegram
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    # Preluăm ultimele 15 mesaje din canalul tău pentru verificarea duplicatelor
    istoric = await client.get_messages(destinatie, limit=15)
    texte_vechi = [m.text for m in istoric if m.text]

    # Procesăm fiecare sursă pe rând
    for sursa in CANALE_SURSA:
        await proceseaza_canal(client, sursa, destinatie, texte_vechi)

    await client.disconnect()
    print("🚀 Misiune finalizată. Toate sursele au fost verificate.")

if __name__ == '__main__':
    asyncio.run(main())
