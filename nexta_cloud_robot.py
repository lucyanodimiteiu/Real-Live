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

# ==========================================
# CANALE SURSĂ (extinse)
# ==========================================
CANALE_SURSA = [
    'nexta_live',
    'TheStudyofWar',
    'osintdefender',
    'mossad_telegram',
    'intelslava',        # Intel Slava Z
    'wartranslated',     # War Translated
]

SEMNATURA = '@real_live_by_luci'
DB_PATH = 'stiri.db'
LOG_PATH = 'bot_log.json'

# ==========================================
# BAZĂ DE DATE SQLite
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS stiri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash_md5 TEXT UNIQUE,
            text_scurt TEXT,
            sursa TEXT,
            score INTEGER,
            data_postare TEXT,
            postat INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def hash_text(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

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
        c.execute('''
            INSERT INTO stiri (hash_md5, text_scurt, sursa, score, data_postare, postat)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (hash_md5, text_scurt[:200], sursa, score, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_top5_azi():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    azi = datetime.now().strftime('%Y-%m-%d')
    c.execute('''
        SELECT text_scurt, sursa, score FROM stiri
        WHERE data_postare LIKE ? AND postat = 1
        ORDER BY score DESC LIMIT 5
    ''', (f'{azi}%',))
    rezultate = c.fetchall()
    conn.close()
    return rezultate

# ==========================================
# LOGGING PERSISTENT
# ==========================================
def log_event(tip, mesaj):
    log = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except:
            log = []
    log.append({
        'timestamp': datetime.now().isoformat(),
        'tip': tip,
        'mesaj': mesaj
    })
    log = log[-500:]  # Păstrăm doar ultimele 500 intrări
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

# ==========================================
# OCR - Extragere text din imagini
# ==========================================
async def extrage_text_din_imagine(file_path):
    try:
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron')
        return text.strip()
    except Exception as e:
        log_event('⚠️ OCR', str(e))
        return ""

# ==========================================
# GENERARE IMAGINE cu Pollinations.ai (100% GRATUIT)
# ==========================================
async def genereaza_imagine(titlu_stire):
    try:
        prompt = f"breaking news illustration, {titlu_stire[:100]}, photorealistic, dramatic lighting, news photography style"
        prompt_encoded = requests.utils.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=576&nologo=true"

        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            img_path = f"generated_img_{hash_text(titlu_stire)[:8]}.jpg"
            with open(img_path, 'wb') as f:
                f.write(response.content)
            log_event('🎨 Imagine', f'Generată pentru: {titlu_stire[:50]}')
            return img_path
    except Exception as e:
        log_event('⚠️ Imagine', str(e))
    return None

# ==========================================
# AI - DeepSeek cu Retry Logic Exponențial
# ==========================================
async def apel_deepseek(prompt, retry=3):
    if not DEEPSEEK_KEY:
        return None

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(retry):
        try:
            response = requests.post(url, json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }, headers=headers, timeout=45)
            return response.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            log_event(f'⚠️ DeepSeek retry {attempt+1}', str(e))
            if attempt < retry - 1:
                await asyncio.sleep(wait)
    return None

async def scoreaza_stire(text):
    """AI evaluează importanța știrii de la 1 la 10"""
    prompt = f"""
Ești editor OSINT. Evaluează importanța acestei știri de la 1 la 10.
Criterii: impact geopolitic, urgență, noutate, relevanță pentru România.
Răspunde DOAR cu un număr întreg între 1 și 10, fără alte cuvinte.

ȘTIRE: {text[:500]}
"""
    rezultat = await apel_deepseek(prompt)
    try:
        return min(max(int(rezultat.strip()), 1), 10)
    except:
        return 5

async def genereaza_rezumat_ai(text_original, text_din_poza=""):
    """Traducere și rescriere profesională în română"""
    prompt = f"""
Ești jurnalist OSINT. Tradu și rescrie în română impecabilă (Reuters style).
Dacă textul din imagine conține info noi, integrează-le natural.

REGULI:
1. Stil fluid, jurnalistic, maxim 3 paragrafe.
2. ELIMINĂ orice link (t.me, http) și orice mențiune @canal_sursa.
3. Rezultatul să fie DOAR știrea în română, fără introduceri sau explicații.

ȘTIRE: {text_original}
TEXT DIN IMAGINE: {text_din_poza}
"""
    rezultat = await apel_deepseek(prompt)
    return rezultat if rezultat else text_original

async def deduplicare_semantica(text_nou, texte_vechi):
    """AI detectează dacă știrea e semantic identică cu una deja postată"""
    if not texte_vechi:
        return False

    sample_vechi = '\n'.join([f"- {t}" for t in texte_vechi[-10:]])
    prompt = f"""
Compară știrea nouă cu lista de știri deja postate.
Răspunde DOAR cu DA dacă descriu același eveniment (chiar dacă sunt reformulate diferit).
Răspunde DOAR cu NU dacă sunt evenimente diferite.

ȘTIRE NOUĂ: {text_nou[:300]}

ȘTIRI VECHI:
{sample_vechi}
"""
    rezultat = await apel_deepseek(prompt)
    if rezultat:
        return 'DA' in rezultat.upper()
    return False

# ==========================================
# REZUMAT ZILNIC TOP 5 (se trimite la ora 20:00)
# ==========================================
async def trimite_rezumat_zilnic(client):
    ora_curenta = datetime.now().hour
    if ora_curenta != 20:
        return

    top5 = get_top5_azi()
    if not top5:
        return

    mesaj = f"📊 **TOP 5 ȘTIRI ALE ZILEI** — {datetime.now().strftime('%d.%m.%Y')}\n\n"
    for i, (text, sursa, score) in enumerate(top5, 1):
        emoji = "🔴" if score >= 9 else "🟠" if score >= 7 else "🟡"
        mesaj += f"{emoji} **{i}.** {text[:150]}...\n"
        mesaj += f"   ⭐ Scor: {score}/10\n\n"

    mesaj += f"\n{SEMNATURA}"

    try:
        await client.send_message(canal_destinatie, mesaj, parse_mode='md')
        log_event('📊 Rezumat', 'Top 5 zilnic trimis cu succes')
        print("✅ Rezumat zilnic Top 5 trimis!")
    except Exception as e:
        log_event('❌ Rezumat', str(e))

# ==========================================
# FUNCȚIA PRINCIPALĂ
# ==========================================
async def main():
    if not all([api_id, api_hash, session_string, canal_destinatie]):
        print("❌ Lipsesc secretele esențiale în GitHub!")
        return

    init_db()
    log_event('🚀 Start', f'Bot pornit la {datetime.now().isoformat()}')

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()

    # Trimite rezumat zilnic dacă e ora 20:00
    await trimite_rezumat_zilnic(client)

    # Preluăm istoricul din DB pentru deduplicare semantică
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT text_scurt FROM stiri ORDER BY id DESC LIMIT 20')
    texte_vechi_db = [row[0] for row in c.fetchall()]
    conn.close()

    stiri_postate = 0

    for sursa in CANALE_SURSA:
        print(f"📡 Scanare canal: @{sursa}")
        log_event('📡 Scanare', f'@{sursa}')

        try:
            async for msg in client.iter_messages(sursa, limit=10):
                if not msg.text and not msg.media:
                    continue

                text_foto = ""
                file_to_send = None
                img_generata = None

                try:
                    # Descarcă media dacă există
                    if msg.media:
                        file_to_send = await msg.download_media()
                        if msg.photo and file_to_send:
                            text_foto = await extrage_text_din_imagine(file_to_send)

                    # Traducere și rescriere AI
                    text_final = await genereaza_rezumat_ai(msg.text or "", text_foto)

                    if not text_final:
                        continue

                    # Verificare duplicat exact (MD5)
                    h = hash_text(text_final)
                    if stire_existenta(h):
                        print(f"⏭️ Duplicat exact, sărit.")
                        continue

                    # Verificare duplicat semantic (AI)
                    if await deduplicare_semantica(text_final, texte_vechi_db):
                        print(f"⏭️ Duplicat semantic, sărit: {text_final[:40]}...")
                        continue

                    # Scoring importanță (postăm doar >= 6)
                    score = await scoreaza_stire(text_final)
                    print(f"⭐ Scor știre: {score}/10")

                    if score < 6:
                        print(f"⏭️ Scor prea mic ({score}), sărit.")
                        log_event('⏭️ Scor mic', f'{score}/10 - {text_final[:50]}')
                        continue

                    # Generare imagine AI dacă nu avem media originală
                    if not file_to_send:
                        img_generata = await genereaza_imagine(text_final[:100])

                    # Formatare mesaj cu emoji în funcție de scor
                    emoji_score = "🔴" if score >= 9 else "🟠" if score >= 7 else "🟡"
                    caption_final = f"{emoji_score} {text_final}\n\n{SEMNATURA}"

                    # Trimitere mesaj
                    media_de_trimis = file_to_send or img_generata

                    if media_de_trimis and os.path.exists(media_de_trimis):
                        await client.send_file(
                            canal_destinatie,
                            media_de_trimis,
                            caption=caption_final,
                            supports_streaming=True
                        )
                    else:
                        await client.send_message(canal_destinatie, caption_final)

                    # Salvare în DB și actualizare cache local
                    salveaza_stire(h, text_final, sursa, score)
                    texte_vechi_db.append(text_final[:200])
                    stiri_postate += 1

                    log_event('✅ Postat', f'@{sursa} | Scor: {score} | {text_final[:60]}')
                    print(f"✅ Postat cu succes din @{sursa} (scor {score})")

                    # Anti-flood: pauză random 5-10 secunde
                    await asyncio.sleep(5 + int(hash_text(text_final)[0], 16) % 6)

                except Exception as msg_error:
                    log_event('❌ Mesaj', str(msg_error))
                    print(f"❌ Eroare la procesare mesaj: {msg_error}")

                finally:
                    # Cleanup fișiere temporare ÎNTOTDEAUNA
                    for f in [file_to_send, img_generata]:
                        if f and os.path.exists(f):
                            try:
                                os.remove(f)
                            except:
                                pass

        except Exception as e:
            log_event('⚠️ Canal', f'@{sursa}: {str(e)}')
            print(f"⚠️ Eroare generală la sursa @{sursa}: {e}")

    log_event('🏁 Final', f'Sesiune completă. Știri postate: {stiri_postate}')
    print(f"\n🏁 Sesiune completă. Total știri postate: {stiri_postate}")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
