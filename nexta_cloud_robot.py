import os
import asyncio
import requests
import pytesseract
from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==========================================
# CONFIGURAȚII
# ==========================================
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY')

try:
    canal_destinatie = int(os.getenv('NEXTALIVEROMANIA_ID'))
except:
    canal_destinatie = os.getenv('NEXTALIVEROMANIA_ID')

CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
SEMNATURA = '@real_live_by_luci'

async def extrage_text_din_imagine(file_path):
    """Citeste textul scris pe poze"""
    try:
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus+heb+ron')
        return text.strip()
    except:
        return ""

async def genereaza_rezumat_ai(text_original, text_din_poza=""):
    """Trimite totul la DeepSeek pentru o traducere unitara"""
    if not DEEPSEEK_KEY: return text_original
    
    context_poza = f"\nTEXT EXTRASE DIN IMAGINE: {text_din_poza}" if text_din_poza else ""
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Tradu si rescrie in romana jurnalistica urmatoarea stire. 
Daca exista text extras din imagine, integreaza informatiile din el in textul final.

REGULI:
1. Elimina link-urile si sursele externe (@canal).
2. Totul trebuie sa fie in limba romana.
3. Semnatura ta nu trebuie sa apara in interiorul textului.

STIRE ORIGINARA: {text_original}
{context_poza}
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }, headers=headers, timeout=40)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return text_original

async def main():
    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()
    
    entitate_dest = await client.get_input_entity(canal_destinatie)
    istoric = await client.get_messages(entitate_dest, limit=15)
    texte_vechi = [m.text for m in istoric if m.text]

    for sursa in CANALE_SURSA:
        async for msg in client.iter_messages(sursa, limit=2):
            if not msg.text and not msg.photo: continue
            
            text_foto = ""
            if msg.photo:
                path = await msg.download_media()
                text_foto = await extrage_text_din_imagine(path)
                if os.path.exists(path): os.remove(path) # Curatam fisierul temporar

            text_final = await genereaza_rezumat_ai(msg.text or "", text_foto)
            
            if not text_final or any(text_final[:50] in (tv or "") for tv in texte_vechi):
                continue
            
            await client.send_message(entitate_dest, f"{text_final}\n\n{SEMNATURA}", file=msg.media)
            print(f"✅ Postat cu OCR din {sursa}")
            await asyncio.sleep(2)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
