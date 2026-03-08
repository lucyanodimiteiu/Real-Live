import os
import asyncio
import re
import subprocess
from telethon import TelegramClient
from telethon.sessions import StringSession
from deep_translator import GoogleTranslator
from gtts import gTTS

# Configurații GitHub Secrets
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
canal_destinatie_raw = os.getenv('NEXTALIVEROMANIA_ID')

# MEGA-LISTA DE SURSE (Nexta + Militare + Intelligence)
CANALE_SURSA = [
    'nexta_live',
    'TheStudyofWar',
    'osintdefender',
    'mossad_telegram',
    'MossadPersian',
    'mossadinfarsi'
]
SEMNATURA_NOASTRA = '@real_live'

def curata_textul_agresiv(text):
    """Elimină link-urile și reclamele de la toate sursele"""
    # 1. Eliminăm link-urile de tip t.me sau telegram.me
    text = re.sub(r'https?://(?:t\.me|telegram\.me)/\S+', '', text)
    
    # 2. Eliminăm mențiunile surselor (Nexta, Mossad, ISW etc.)
    pattern_surse = r'[@#]?(nexta|TheStudyofWar|osint|mossad|intel_sky)(?:_live|_tv|_official|_telegram)?'
    text = re.sub(pattern_surse, '', text, flags=re.IGNORECASE)
    
    # 3. Curățăm spațiile multiple
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

async def proceseaza_canal(client, canal_sursa, canal_destinatie, texte_vechi, translator):
    print(f"📡 Scanăm: @{canal_sursa}...")
    try:
        messages = await client.get_messages(canal_sursa, limit=3)
        for msg in reversed(messages):
            if not msg.text or len(msg.text) < 5:
                continue

            # TRADUCEM (Indiferent că e rusă, persană sau engleză)
            text_tradus = translator.translate(msg.text)
            text_curat = curata_textul_agresiv(text_tradus)
            text_final = f"{text_curat}\n\n{SEMNATURA_NOASTRA}"

            # Verificăm duplicate
            if any(text_curat[:50] in (tv or "") for tv in texte_vechi):
                continue

            if msg.video:
                print(f"🎥 Dublaj voce pentru clip de la @{canal_sursa}...")
                video_path = await msg.download_media(file=f'vid_{msg.id}.mp4')
                tts = gTTS(text=text_curat[:400], lang='ro') # Limită scurtă pentru viteză
                tts.save(f"voce_{msg.id}.mp3")
                
                output_video = f"final_{msg.id}.mp4"
                cmd = ['ffmpeg', '-y', '-i', video_path, '-i', f"voce_{msg.id}.mp3", '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-shortest', output_video]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                await client.send_message(canal_destinatie, message=text_final, file=output_video)
                os.remove(video_path); os.remove(f"voce_{msg.id}.mp3"); os.remove(output_video)
            else:
                await client.send_message(canal_destinatie, message=text_final, file=msg.media)
            
            print(f"✅ Postat de la @{canal_sursa}")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"❌ Eroare la @{canal_sursa}: {e}")

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
    
    istoric = await client.get_messages(canal_destinatie, limit=10)
    texte_vechi = [m.text for m in istoric if m.text]
    translator = GoogleTranslator(source='auto', target='ro')

    for sursa in CANALE_SURSA:
        await proceseaza_canal(client, sursa, canal_destinatie, texte_vechi, translator)

    await client.disconnect()
    print("Misiune finalizată.")

if __name__ == '__main__':
    asyncio.run(main())
