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
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KY')

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

# ==========================================
# BAZĂ DE DATE SQLite & LOGGING
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stiri (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash_md5 TEXT UNIQUE, text_scurt TEXT,
                    sursa TEXT, score INTEGER,
                    data_postare TEXT, postat INTEGER DEFAULT 0)''')
    # Adaugam campul pentru trackerul de rezumat (daca nu exista)
    try:
        c.execute('ALTER TABLE stiri ADD COLUMN trimis_rezumat INTEGER DEFAULT 0')
    except:
        pass
    conn.commit()
    conn.close()

def hash_text(text): return hashlib.md5(text.encode('utf-8')).hexdigest()

def stire_existenta(hash_md5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM stiri WHERE hash_md5 = ?', (hash_md5,))
    result = c.fetchone()
    conn.close()
    return result is not None

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
# AI - DEEPSEEK (CONSOLIDAT: Scoring, Traducere, Deduplicare într-un APEL)
# ==========================================
async def evalueaza_stire_ai(text_nou, texte_vechi, sursa_img_text="", retry=2):
    if not DEEPSEEK_KEY: return None
    
    sample_vechi = '\n'.join([f"- {t}" for t in texte_vechi[-10:]])
    prompt = f"""
Ești un AI OSINT ultra-eficient. Analizează ȘTIREA NOUĂ (și opțional textul din imagine).
1. TRADUCE/RESCRIE în limba română (stil Reuters, maxim 3 paragrafe, fără linkuri/atribuiri).
2. SCORING de la 1 la 10 (importanță geopolitică/urgență/noutate).
3. DEDUPLICARE: Verifică dacă evenimentul e deja în ȘTIRI VECHI (chiar și rescris). Returnează true/false.

Răspunde STRICT în format JSON, fără alte comentarii:
{{"scor": 8, "duplicat": false, "text_ro": "Traducerea finală aici..."}}

ȘTIRE NOUĂ: {text_nou[:600]}
TEXT IMAGINE: {sursa_img_text[:300]}
ȘTIRI VECHI: {sample_vechi}
"""
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    for attempt in range(retry):
        try:
            resp = requests.post("https://api.deepseek.com/v1/chat/completions", json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            }, headers=headers, timeout=30)
            content = resp.json()['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            log_event(f'⚠️ DeepSeek retry {attempt+1}', str(e))
            if attempt < retry - 1: await asyncio.sleep(2 ** attempt)
    return None

# ==========================================
# REZUMAT ZILNIC (08:00 și 20:00 - Ora Locală Olanda/CET)
# ==========================================
async def verifica_si_trimite_rezumat(client):
    import pytz
    tz_olanda = pytz.timezone('Europe/Amsterdam')
    ora = datetime.now(tz_olanda).hour
    
    # Rulam la 08:00 (dimineata) si 20:00 (seara) pe ora Olandei
    if ora not in [8, 20]:
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Preia top 5 stiri din ultimele 12 ore (aprox) care n-au mai fost in rezumat
    c.execute('''
        SELECT text_scurt, sursa, score, id FROM stiri
        WHERE postat = 1 AND trimis_rezumat = 0
        ORDER BY score DESC, data_postare DESC LIMIT 5
    ''')
    top5 = c.fetchall()
    
    if len(top5) >= 3: # Trimitem doar daca s-au strans macar 3 stiri importante
        ora_olanda_str = datetime.now(tz_olanda).strftime('%d.%m.%Y - %H:00 (Ora Locală)')
        mesaj = f"📊 **ANALIZA EXCLUSIVĂ: TOP EVENIMENTE ({ora_olanda_str})**\n\n"
        ids_actualizate = []
        for i, (text, sursa, score, _id) in enumerate(top5, 1):
            emoji = "🔴" if score >= 9 else "🟠" if score >= 7 else "🟡"
            mesaj += f"{emoji} **{i}.** {text[:180]}...\n   ⭐ Relevanță: {score}/10\n\n"
            ids_actualizate.append(str(_id))
        
        mesaj += f"\n{SEMNATURA}"
        
        try:
            await client.send_message(canal_destinatie, mesaj, parse_mode='md')
            log_event('📊 Rezumat', 'Top-ul la 12h a fost trimis cu succes')
            print("✅ Rezumatul Top-urilor trimis!")
            # Marcăm știrile ca fiind deja 'consumate' pentru rezumatul curent
            if ids_actualizate:
                c.execute(f"UPDATE stiri SET trimis_rezumat = 1 WHERE id IN ({','.join(ids_actualizate)})")
                conn.commit()
        except Exception as e:
            log_event('❌ Eroare Rezumat', str(e))
    conn.close()

# ==========================================
# CORE LOGIC - PROCESARE ASINCRONĂ & LAZY LOAD
# ==========================================
async def proceseaza_mesaj(client, msg, sursa, texte_vechi_db):
    if not msg.text and not msg.media: return None
    
    # [1] Pre-evaluare brută (LAZY LOAD). NU descărcăm poze/video încă.
    text_brut = msg.text or ""
    
    # Euristică rapidă: dacă e doar o poză/video fără text (sau foarte scurt), tragem poza pentru OCR.
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

    # [2] APEL AI CONSOLIDAT (1 cerere în loc de 3)
    eval_ai = await evalueaza_stire_ai(text_de_analizat, texte_vechi_db, text_foto)
    if not eval_ai: 
        if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
        return None

    scor = eval_ai.get('scor', 5)
    duplicat = eval_ai.get('duplicat', False)
    text_final = eval_ai.get('text_ro', "")

    # Filtre de respingere rapidă (MODIFICAT: BYPASS PENTRU NEXTA_LIVE)
    h = hash_text(text_final)
    
    # 1. Daca stirea e deja in baza noastra de date cu MD5 identic, oprim oricum (sa nu repetam in bucla)
    if stire_existenta(h) or not text_final:
        if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
        return None

    # NOUL BYPASS ABSOLUT (Daca e nexta_live, nu il mai trecem prin evaluarea deepseek de duplicat/scor)
    if sursa == "nexta_live":
        # Pentru nexta_live ignoram variabila "duplicat" (care a dat false-positive din cauza deepseek)
        pass 
    else:
        # 2. Daca stirea NU este de la nexta_live, aplicam filtrele dure (Scor >= 6 si Non-Duplicat Semantic)
        if duplicat or scor < 6:
            log_event('⏭️ Sărit', f"Scor:{scor} | Dup:{duplicat} | {text_final[:30]}")
            if file_to_send and os.path.exists(file_to_send): os.remove(file_to_send)
            return None

    # [3] POST-EVALUARE (Acum descărcăm media dacă nu am făcut-o și scorul merită)
    img_generata = None
    if msg.media and not file_to_send:
        file_to_send = await msg.download_media()
    elif not msg.media:
        img_generata = await genereaza_imagine(text_final[:100])

    # Formatare finală
    emoji_score = "🔴" if scor >= 9 else "🟠" if scor >= 7 else "🟡"
    caption_final = f"{emoji_score} {text_final}\n\n{SEMNATURA}"
    media_de_trimis = file_to_send or img_generata

    try:
        if media_de_trimis and os.path.exists(media_de_trimis):
            await client.send_file(canal_destinatie, media_de_trimis, caption=caption_final, supports_streaming=True)
        else:
            await client.send_message(canal_destinatie, caption_final)

        salveaza_stire(h, text_final, sursa, scor)
        texte_vechi_db.append(text_final[:200])
        log_event('✅ Postat', f'@{sursa} | Scor: {scor}')
        print(f"✅ Postat din @{sursa} (scor {scor})")
        
        # Anti-flood mic (3s e suficient pe Telegram API dacă nu se dă spam abuziv)
        await asyncio.sleep(3)
        return True
    except Exception as e:
        log_event('❌ Mesaj Error', str(e))
    finally:
        for f in [file_to_send, img_generata]:
            if f and os.path.exists(f): 
                try: os.remove(f)
                except: pass
    return False

# ==========================================
# MAIN LOOP
# ==========================================
async def main():
    init_db()
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()

    # Apelam functia de top 5 (modificata sa se declanseze fix acum)
    await verifica_si_trimite_rezumat(client)

    conn = sqlite3.connect(DB_PATH)
    texte_vechi_db = [row[0] for row in conn.cursor().execute('SELECT text_scurt FROM stiri ORDER BY id DESC LIMIT 20').fetchall()]
    conn.close()

    stiri_postate = 0

    for sursa in CANALE_SURSA:
        print(f"📡 Scanare: @{sursa}")
        try:
            mesaje = await client.get_messages(sursa, limit=10)
            
            # Procesare concurentă limitată: 3 mesaje simultan
            for i in range(0, len(mesaje), 3):
                batch = mesaje[i:i+3]
                tasks = [proceseaza_mesaj(client, m, sursa, texte_vechi_db) for m in batch]
                rezultate = await asyncio.gather(*tasks, return_exceptions=True)
                stiri_postate += sum([1 for r in rezultate if r is True])

        except Exception as e:
            log_event('⚠️ Canal', f'@{sursa}: {str(e)}')

    print(f"\n🏁 Complet. Postate: {stiri_postate}")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
