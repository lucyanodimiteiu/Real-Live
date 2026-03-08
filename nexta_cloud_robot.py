import os
import asyncio
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession

# ==========================================
# CONFIGURAȚII
# ==========================================
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
session_string = os.getenv('TELEGRAM_SESSION')

try:
    canal_destinatie = int(os.getenv('NEXTALIVEROMANIA_ID'))
except:
    canal_destinatie = os.getenv('NEXTALIVEROMANIA_ID')

DEEPSEEK_KEY = os.getenv('DEEPSEEK_API_KEY')

# ==========================================
# CONFIGURARE SURSE ȘI SEMNĂTURĂ NOUĂ
# ==========================================
CANALE_SURSA = ['nexta_live', 'TheStudyofWar', 'osintdefender', 'mossad_telegram']
SEMNATURA = '@real_live_by_luci' # Semnătura ta personalizată

async def genereaza_rezumat_ai(text_original):
    if not DEEPSEEK_KEY:
        return text_original
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    
    # Am adăugat instrucțiunea de a ELIMINA orice link-uri sau nume de canale sursă
    prompt = f"""
Tradu si rescrie acest text in romana jurnalistica impecabila. 
REGULI STRICTE:
1. Elimina absolut orice link (http/https) sau mentiune de tip @nume_canal din textul original.
2. Nu mentiona sursa stirii.
3. Pastreaza doar faptele, cifrele si locatiile.

TEXT ORIGINAL: {text_original}
"""
    try:
        response = requests.post(url, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3 # Scădem temperatura pentru mai multă precizie
        }, headers=headers, timeout=30)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return None

async def main():
    if not all([api_id, api_hash, session_string, canal_destinatie]):
        print("Lipsesc secretele!")
        return

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    await client.connect()

    try:
        entitate_dest = await client.get_input_entity(canal_destinatie)
        istoric = await client.get_messages(entitate_dest, limit=10)
        texte_vechi = [m.text for m in istoric if m.text]
    except Exception as e:
        print(f"Eroare canal: {e}")
        return

    for sursa in CANALE_SURSA:
        try:
            async for msg in client.iter_messages(sursa, limit=2):
                if not msg.text or len(msg.text) < 10:
                    continue
                
                text_nou = await genereaza_rezumat_ai(msg.text)
                
                if not text_nou or any(text_nou[:50] in (tv or "") for tv in texte_vechi):
                    continue
                
                # Aici se pune doar semnătura ta curată
                await client.send_message(entitate_dest, f"{text_nou}\n\n{SEMNATURA}", file=msg.media)
                print(f"✅ Postat curat din {sursa}")
                await asyncio.sleep(2)
        except Exception as e:
            print(f"Eroare sursa {sursa}: {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
