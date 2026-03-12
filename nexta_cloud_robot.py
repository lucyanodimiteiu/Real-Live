import os
import asyncio
import hashlib
import sqlite3
import json
import requests
import pytesseract
from PIL import Image
from datetime import datetime
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

CANALE_SURSA = [
    'nexta_live', 'TheStudyofWar', 'osintdefender', 
    'mossad_telegram', 'intelslava', 'wartranslated'
]

SEMNATURA = '@real_live_by_luci'
DB_PATH = 'stiri.db'
LOG_PATH = 'bot_log.json'
BLACKLIST_FILE = 'processed_links.txt' # Strategia transplantată

# ==========================================
# STRATEGIA DE DE-DUPLICARE (FILE-BASED)
# ==========================================
def hash_text(text): 
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def is_blacklisted(h):
    if not os.path.exists(BLACKLIST_FILE):
        return False
    try:
        with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            return h in f.read()
    except Exception as e:
        log_event('⚠️ Blacklist Read Error', str(e))
        return False

def add_to_blacklist(h):
    try:
        with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
            f.write(h + '\n')
    except Exception as e:
        log_event('⚠️ Blacklist Write Error', str(e))

# ==========================================
# BAZĂ DE DATE SQLite (Pentru Rezumat/Top)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stiri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash_md5 TEXT UNIQUE, text_scurt TEXT,
                    sursa TEXT, score INTEGER,
                    data_postare TEXT, postat INTEGER DEFAULT 0,
                    trimis_rezumat INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def salveaza_stire(hash_md5, text_scurt, sursa, score):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO stiri (hash_md5, text_scurt, sursa, score, data_postare, postat) VALUES (?, ?, ?, ?, ?, 1)', 
                  (hash_md5, text_scurt[:200], sursa, score, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError: pass
    conn.close()

def log_event(tip, mesaj):
    log = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r', encoding='utf-8') as f: log = json.load(f)
        except: pass
    log.append({'timestamp': datetime.now().isoformat(), 'tip': tip, 'mesaj': mesaj})
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(log[-500:], f, ensure_ascii=False, indent=2)

# ==========================================
# OCR & GENERARE IMAGINI
# ==========================================
async def extrage_text_din_imagine(file_path):
    try: return pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron').strip()
    except Exception as e: log_event('⚠️ OCR', str(e)); return ""

async def genereaza_imagine(titlu_stire):
    try:
        prompt_encoded = requests.utils.quote(f"breaking news illustration, {titlu_stire[:100]}, photorealistic, dramatic lighting, news photography style")
        resp = requests.get(f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=576&nologo=true", timeout=30)
        if resp.status_code == 200:
            img_path = f"generated_img_{hash_text(titlu_stire)[:8]}.jpg"
            with open(img_path, 'wb') as f: f.write(resp.content)
            return img_path
    except Exception as e: log_event('⚠️ Imagine', str(e))
    return None

# ==========================================
# AI - DEEPSEEK
# ==========================================
async def evalueaza_stire_ai(text_nou, texte_vechi, sursa_img_text="", retry=2):
    if not DEEPSEEK_KEY: return None
    sample_vechi = '\n'.join([f"- {t}" for t in texte_vechi[-10:]])
    prompt = f"""
Ești un AI OSINT ultra-eficient. Analizează ȘTIREA NOUĂ.
Suntem în anul 2026. Donald Trump este președintele SUA.
1. TRADUCE/RESCRIE în română (stil Reuters, maxim 3 paragrafe).
2. SCORING 1-10.
3. DEDUPLICARE SEMANTICĂ: Returnează true dacă evenimentul e deja în ȘTIRI VECHI.

Răspunde JSON: {{"scor": 8, "duplicat": false, "text_ro": "..."}}

ȘTIRE NOUĂ: {text_nou[:600]}
TEXT IMAGINE: {sursa_img_text[:300]}
ȘTIRI VECHI: {sample_vechi}
"""
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    for attempt in range(retry):
        try:
            resp = requests.post("https://api.deepseek.com/v1/chat/completions", json={
                "model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2, "response_format": {"type": "json_object"}
            }, headers=headers, timeout=30)
            return resp.json()['choices'][0]['message']['content']
        except: await asyncio.sleep(2 ** attempt)
    return None

# ==========================================
# PROCESARE ASINCRONĂ
# ==========================================
async def proceseaza_mesaj(client, msg, sursa, texte_vechi_db):
    if not msg.text and not msg.media: return None

    # [1] IDENTIFICATOR UNIC (Adaptat pentru Telegram + Web)
    unique_id = None
    if hasattr(msg, 'chat_id') and msg.chat_id and msg.id:
        unique_id = f"{msg.chat_id}:{msg.id}"
    elif hasattr(msg, 'link') and msg.link:
        unique_id = msg.link
    else:
        unique_id = (msg.text or "")[:150]

    if not unique_id: return None
    h = hash_text(unique_id)

    # [2] VERIFICARE BLACKLIST (Strategia Automatizare-Stiri)
    if is_blacklisted(h):
        return None # Oprim imediat orice procesare

    # [3] LAZY LOAD & OCR
    text_brut = msg.text or ""
    text_foto = ""
    file_to_send = None
    if len(text_brut) < 20 and msg.media:
        file_to_send = await msg.download_media()
        if msg.photo and file_to_send:
            text_foto = await extrage_text_din_imagine(file_to_send)

    text_de_analizat = text_brut if len(text_brut) >= 20 else text_foto
    if not text_de_analizat:
        if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
        return None

    # [4] APEL AI
    res_raw = await evalueaza_stire_ai(text_de_analizat, texte_vechi_db, text_foto)
    if not res_raw: return None
    eval_ai = json.loads(res_raw)

    scor = eval_ai.get('scor', 5)
    duplicat_ai = eval_ai.get('duplicat', False)
    text_final = eval_ai.get('text_ro', "")

    # Filtre (BYPASS Nexta_Live)
    if sursa != "nexta_live":
        if duplicat_ai or scor < 6:
            if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
            return None

    # [5] MEDIA & POSTARE
    img_generata = None
    if msg.media and not file_to_send:
        file_to_send = await msg.download_media()
    elif not msg.media:
        img_generata = await genereaza_imagine(text_final[:100])

    caption_final = f"{'🔴' if scor >= 9 else '🟠' if scor >= 7 else '🟡'} {text_final}\n\n{SEMNATURA}"
    media_de_trimis = file_to_send or img_generata

    try:
        if media_de_trimis and os.path.exists(media_de_trimis):
            await client.send_file(canal_destinatie, media_de_trimis, caption=caption_final)
        else:
            await client.send_message(canal_destinatie, caption_final)

        # SALVARE ÎN BLACKLIST DOAR DUPĂ SUCCES
        add_to_blacklist(h)
        salveaza_stire(h, text_final, sursa, scor)
        texte_vechi_db.append(text_final[:200])
        print(f"✅ Postat: @{sursa}")
        await asyncio.sleep(3)
        return True
    except Exception as e:
        log_event('❌ Post Error', str(e))
    finally:
        for f in [file_to_send, img_generata]:
            if f and os.path.exists(f): os.remove(f)
    return False

# ==========================================
# MAIN
# ==========================================
async def main():
    init_db()
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()

    conn = sqlite3.connect(DB_PATH)
    texte_vechi_db = [row[0] for row in conn.cursor().execute('SELECT text_scurt FROM stiri ORDER BY id DESC LIMIT 20').fetchall()]
    conn.close()

    for sursa in CANALE_SURSA:
        try:
            mesaje = await client.get_messages(sursa, limit=10)
            for m in mesaje:
                await proceseaza_mesaj(client, m, sursa, texte_vechi_db)
        except Exception as e: log_event('⚠️ Canal', f'@{sursa}: {str(e)}')

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
