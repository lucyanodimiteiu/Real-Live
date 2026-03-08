import os
import asyncio
import requests
import pytesseract
from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==========================================
# CONFIGURAȚII GITHUB SECRETS
# ==========================================
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY')

try:
    canal_destinatie = int(os.getenv('NEXTALIVEROMANIA_ID'))
except:
    canal_destinatie = os.getenv('NEXTALIVEROMANIA_ID')

# Sursele tale și semnătura cerută
CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
SEMNATURA = '@real_live_by_luci'

async def extrage_text_din_imagine(file_path):
    """Extrage textul de pe poze (OCR)"""
    try:
        # Detectează text în engleză, rusă, ebraică și română
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron')
        return text.strip()
    except:
        return ""

async def genereaza_rezumat_ai(text_original, text_din_poza=""):
    """DeepSeek: Traducere și adaptare fără link-uri/surse"""
    if not DEEPSEEK_KEY: return text_original
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Ești jurnalist OSINT. Tradu și rescrie în română jurnalistă impecabilă (Reuters style).
Dacă textul din imagine conține info noi, integrează-le.

REGULI:
1. Stil fluid, fără liste.
2. ELIMINĂ orice link (t.me, http) și orice mențiune @canal_sursa.
3. Rezultatul să fie DOAR știrea în română.

ȘTIRE: {text_original}
TEXT DIN IMAGINE: {text_din_poza}
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }, headers=headers, timeout=45)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return text_original

async def main():
    if not all([api_id, api_hash, session_string, canal_destinatie, DEEPSEEK_KEY]):
        print("❌ Lipsesc secretele!")
        return

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    try:
        entitate_dest = await client.get_input_entity(canal_destinatie)
        istoric = await client.get_messages(entitate_dest, limit=20)
        texte_vechi = [m.text for m in istoric if m.text]
    except Exception as e:
        print(f"❌ Eroare canal: {e}")
        return

    for sursa in CANALE_SURSA:
        print(f"📡 Scan: @{sursa}")
        try:
            # Luăm ultimele 2 mesaje din fiecare sursă
            async for msg in client.iter_messages(sursa, limit=2):
                if not msg.text and not msg.media: continue
                
                text_foto = ""
                # OCR doar dacă este imagine (nu video)
                if msg.photo:
                    tmp_path = await msg.download_media()
                    text_foto = await extrage_text_din_imagine(tmp_path)
                    if os.path.exists(tmp_path): os.remove(tmp_path)

                text_final = await genereaza_rezumat_ai(msg.text or "", text_foto)
                
                # Evităm duplicatele (primele 60 caractere)
                if not text_final or any(text_final[:60] in (tv or "") for tv in texte_vechi):
                    continue
                
                # POSTARE: Trimitem Media (Video/Foto) + Text separat
                if msg.media:
                    # Trimite fișierul (Video sau Imagine)
                    await client.send_message(entitate_dest, file=msg.media)
                    # Trimite textul tradus sub fișier
                    await client.send_message(entitate_dest, f"{text_final}\n\n{SEMNATURA}")
                else:
                    # Doar text dacă nu există media
                    await client.send_message(entitate_dest, f"{text_final}\n\n{SEMNATURA}")
                
                print(f"✅ Postat media/text din @{sursa}")
                await asyncio.sleep(3)
                
        except Exception as e:
            print(f"⚠️ Eroare la @{sursa}: {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
