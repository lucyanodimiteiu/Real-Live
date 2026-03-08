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

# Configurare surse și semnătura ta
CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
SEMNATURA = '@real_live_by_luci'

async def extrage_text_din_imagine(file_path):
    """Extrage textul scris direct pe poze (OCR)"""
    try:
        # Folosește Tesseract pentru a citi din imagine (engleză, rusă, ebraică, română)
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron')
        return text.strip()
    except Exception as e:
        print(f"⚠️ OCR Error: {e}")
        return ""

async def genereaza_rezumat_ai(text_original, text_din_poza=""):
    """Trimite totul la DeepSeek pentru traducere și adaptare stilistică"""
    if not DEEPSEEK_KEY: return text_original
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Ești un jurnalist OSINT de elită. Tradu și rescrie următoarea știre în limba română.
Dacă există text extras din imagine, integrează acele informații esențiale în corpul știrii.

REGULI STRICTE:
1. Stil jurnalistic sobru, de impact (Reuters/Bloomberg).
2. ELIMINĂ orice link-uri (t.me, http) și orice mențiune a canalelor sursă (@nume).
3. Rezultatul trebuie să fie un text fluid, fără liste cu puncte.
4. Totul trebuie să fie în limba română.

ȘTIRE ORIGINALĂ: {text_original}
TEXT DIN IMAGINE (DACĂ EXISTĂ): {text_din_poza}
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1500
        }, headers=headers, timeout=45)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return text_original

async def main():
    if not all([api_id, api_hash, session_string, canal_destinatie, DEEPSEEK_KEY]):
        print("❌ EROARE: Lipsesc secretele în GitHub!")
        return

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    # Obținem entitatea canalului destinație
    try:
        entitate_dest = await client.get_input_entity(canal_destinatie)
        # Preluăm istoricul pentru a evita duplicatele
        istoric = await client.get_messages(entitate_dest, limit=15)
        texte_vechi = [m.text for m in istoric if m.text]
    except Exception as e:
        print(f"❌ Eroare acces canal destinație: {e}")
        return

    for sursa in CANALE_SURSA:
        print(f"📡 Scanăm sursa: @{sursa}")
        try:
            async for msg in client.iter_messages(sursa, limit=2):
                if not msg.text and not msg.photo: continue
                
                # Procesare OCR dacă există poză
                text_foto = ""
                if msg.photo:
                    tmp_path = await msg.download_media()
                    text_foto = await extrage_text_din_imagine(tmp_path)
                    if os.path.exists(tmp_path): os.remove(tmp_path)

                # Generare text prin DeepSeek
                text_final = await genereaza_rezumat_ai(msg.text or "", text_foto)
                
                # Verificare duplicate (primele 50 de caractere)
                if not text_final or any(text_final[:50] in (tv or "") for tv in texte_vechi):
                    continue
                
                # --- SOLUȚIA PENTRU TEXT LUNG ---
                # Trimitem media separat de text pentru a evita eroarea CaptionTooLong
                if msg.photo:
                    await client.send_message(entitate_dest, file=msg.media)
                    await client.send_message(entitate_dest, f"{text_final}\n\n{SEMNATURA}")
                else:
                    await client.send_message(entitate_dest, f"{text_final}\n\n{SEMNATURA}")
                
                print(f"✅ Postat cu succes din @{sursa}")
                await asyncio.sleep(3) # Pauză anti-spam
                
        except Exception as e:
            print(f"⚠️ Eroare la procesarea sursei @{sursa}: {e}")

    await client.disconnect()
    print("🚀 Misiune terminată cu succes!")

if __name__ == '__main__':
    asyncio.run(main())
