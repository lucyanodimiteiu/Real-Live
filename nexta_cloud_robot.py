
import os
import asyncio
import re
import subprocess
from telethon import TelegramClient
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator
from gtts import gTTS

# Configurații
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')

CANAL_SURSA = 'nexta_live'
SEMNATURA_NOASTRA = '@real_live'

def curata_textul_agresiv(text):
    """Elimină absolut orice urmă de Nexta folosind Regex"""
    # 1. Eliminăm link-urile de tip t.me sau telegram.me
    text = re.sub(r'https?://(?:t\.me|telegram\.me)/\S+', '', text)
    
    # 2. Eliminăm orice mențiune a cuvântului NEXTA (indiferent de litere mari/mici)
    # Caută @nexta, #nexta, nexta_live, etc.
    text = re.sub(r'[@#]?nexta(?:_live|_tv)?', '', text, flags=re.IGNORECASE)
    
    # 3. Eliminăm spațiile multiple sau liniile goale lăsate în urmă
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()

async def main():
    if not api_id or not api_hash or not session_string or not canal_destinatie_raw:
        print("EROARE: Lipsesc secretele!")
        return

    try:
        canal_destinatie = int(canal_destinatie_raw) if str(canal_destinatie_raw).startswith('-100') else canal_destinatie_raw
    except:
        canal_destinatie = canal_destinatie_raw

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    # Verificăm duplicatele (ca să nu mai apară de 3 ori)
    istoric = await client.get_messages(canal_destinatie, limit=5)
    texte_vechi = [m.text for m in istoric if m.text]

    print(f"Preluăm știri de pe {CANAL_SURSA}...")
    try:
        messages = await client.get_messages(CANAL_SURSA, limit=3)
        translator = GoogleTranslator(source='auto', target='ro')

        for msg in reversed(messages):
            if msg.text and len(msg.text) > 5:
                # TRADUCEM ÎNTÂI
                text_tradus = translator.translate(msg.text)
                
                # CURĂȚĂM AGRESIV
                text_curat = curata_textul_agresiv(text_tradus)
                
                # ADĂUGĂM SEMNĂTURA TA
                text_final = f"{text_curat}\n\n{SEMNATURA_NOASTRA}"
                
                # Verificăm dacă știrea e deja pe canal (comparăm doar textul curat)
                if any(text_curat[:50] in (tv or "") for tv in texte_vechi):
                    print("⏭️ Știrea există deja. Skip.")
                    continue

                if msg.video:
                    print("🎥 Procesăm video cu dublaj...")
                    video_path = await msg.download_media(file='original_video.mp4')
                    tts = gTTS(text=text_curat, lang='ro')
                    tts.save("voce_ro.mp3")
                    
                    output_video = "video_dublat.mp4"
                    cmd = ['ffmpeg', '-y', '-i', video_path, '-i', 'voce_ro.mp3', '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-shortest', output_video]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    await client.send_message(canal_destinatie, message=text_final, file=output_video)
                    os.remove(video_path); os.remove("voce_ro.mp3"); os.remove(output_video)
                else:
                    await client.send_message(canal_destinatie, message=text_final, file=msg.media)
                
                print(f"✅ Postat curat cu semnătura {SEMNATURA_NOASTRA}")
                await asyncio.sleep(2)

    except Exception as e:
        print(f"❌ Eroare: {e}")

    print("Misiune finalizată.")

if __name__ == '__main__':
    asyncio.run(main())
