import os
import asyncio
import requests
import pytesseract
from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==========================================
# CONFIGURAȚII GITHUB SECRETS (Preluat din YAML)
# ==========================================
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY')

try:
    # Încercăm să convertim ID-ul în întreg dacă este numeric
    canal_destinatie = int(os.getenv('NEXTALIVEROMANIA_ID'))
except:
    canal_destinatie = os.getenv('NEXTALIVEROMANIA_ID')

# Canale sursă OSINT și Semnătura ta
CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
SEMNATURA = '@real_live_by_luci'

async def extrage_text_din_imagine(file_path):
    """OCR: Detectează text în mai multe limbi de pe poze"""
    try:
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron')
        return text.strip()
    except Exception as e:
        print(f"⚠️ Eroare OCR: {e}")
        return ""

async def genereaza_rezumat_ai(text_original, text_din_poza=""):
    """DeepSeek: Traducere și adaptare profesională"""
    if not DEEPSEEK_KEY: return text_original
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Ești jurnalist OSINT. Tradu și rescrie în română impecabilă (Reuters style).
Dacă textul din imagine conține info noi, integrează-le natural.

REGULI:
1. Stil fluid, jurnalistic.
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
    except Exception as e:
        print(f"⚠️ Eroare AI: {e}")
        return text_original

async def main():
    if not all([api_id, api_hash, session_string, canal_destinatie]):
        print("❌ Lipsesc secretele esențiale în GitHub!")
        return

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    # Verificăm ultimele postări de pe canalul tău ca să nu repetăm știrea
    try:
        # Preluăm o listă mai mare pentru siguranță (ultimele 30)
        istoric = await client.get_messages(canal_destinatie, limit=30)
        texte_vechi = [m.text[:100] for m in istoric if m.text]
    except Exception as e:
        print(f"❌ Eroare acces canal destinație: {e}")
        return

    for sursa in CANALE_SURSA:
        print(f"📡 Scanare canal: @{sursa}")
        try:
            # Citim ultimele 10 mesaje (ideal pentru rularea la 20 min)
            async for msg in client.iter_messages(sursa, limit=10):
                if not msg.text and not msg.media: continue
                
                text_foto = ""
                file_to_send = None
                
                # Gestionare Media (Video/Foto/Document)
                if msg.media:
                    # Descarcă media local (necesar pentru fișiere mari și OCR)
                    file_to_send = await msg.download_media()
                    
                    if msg.photo and file_to_send:
                        text_foto = await extrage_text_din_imagine(file_to_send)

                # Procesare text prin AI
                text_final = await genereaza_rezumat_ai(msg.text or "", text_foto)
                
                if not text_final:
                    if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
                    continue
                
                # Verificare dacă știrea a fost deja postată (comparăm primele 100 caractere)
                if any(text_final[:100] in (tv or "") for tv in texte_vechi):
                    print(f"⏭️ Sărit (deja postat): {text_final[:40]}...")
                    if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
                    continue
                
                # Formatează mesajul final cu semnătură
                caption_final = f"{text_final}\n\n{SEMNATURA}"
                
                # Trimitere unificată (Media + Caption într-un singur balon)
                try:
                    if file_to_send:
                        # supports_streaming=True rezolvă problema videoclipurilor mari (>5MB)
                        await client.send_file(canal_destinatie, file_to_send, caption=caption_final, supports_streaming=True)
                        os.remove(file_to_send)
                    else:
                        await client.send_message(canal_destinatie, caption_final)
                    
                    print(f"✅ Postat cu succes din @{sursa}")
                    # Adăugăm știrea nouă în lista locală ca să nu o repostăm în aceeași sesiune
                    texte_vechi.append(text_final[:100])
                    await asyncio.sleep(5) # Protecție anti-flood
                except Exception as send_error:
                    print(f"❌ Eroare la trimitere: {send_error}")

        except Exception as e:
            print(f"⚠️ Eroare generală la sursa @{sursa}: {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
