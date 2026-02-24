import os
import logging
import requests
import threading
import urllib.parse
from flask import Flask
import pytz
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN ---
logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

genai.configure(api_key=GEMINI_KEY)

# --- SERVIDOR WEB ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Francine V35 Online. 🍷", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- MOTOR TMDB ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        print(f"🔎 Buscando en TMDB: {q}", flush=True)
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", 
                               params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, 
                               timeout=10).json()
    except Exception as e:
        print(f"❌ Error TMDB: {e}", flush=True)
    return None

# --- MANEJADOR DE MENSAJES ---
async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    print(f"📥 Mensaje recibido: {user_txt}", flush=True)
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    
    prompt = f"Sos Francine, sommelier de cine argentina. Respondé en 2 frases cortas. RECOMENDÁ UNA PELÍCULA. Etiqueta obligatoria: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        # Configuración para evitar bloqueos por seguridad
        model = genai.GenerativeModel('gemini-1.5-flash',
                                    safety_settings=[
                                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                                    ])
        
        response = model.generate_content(prompt)
        txt = response.text
        print(f"🤖 Respuesta IA: {txt}", flush=True)
        
        if "[BUSCAR:" in txt:
            p_query = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(p_query)
            
            if peli:
                tit = peli.get('title')
                orig = peli.get('original_title', tit)
                año = peli.get('release_date', '????')[:4]
                dur = peli.get('runtime', 0)
                resumen = peli.get('overview', 'Sin descripción.')
                imdb = peli.get('imdb_id')
                poster = peli.get('poster_path')
                
                zona = pytz.timezone('America/Argentina/Buenos_Aires')
                ahora = datetime.now(zona)
                fin = ahora + timedelta(minutes=dur) if dur else ahora
                
                trailer_url = None
                for v in peli.get('videos', {}).get('results', []):
                    if v['site'] == 'YouTube' and v['type'] == 'Trailer':
                        trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
                        break

                cuerpo = txt.split("[BUSCAR:")[0].strip()
                final_txt = (
                    f"🍷 {cuerpo}\n\n"
                    f"🎬 **{tit} ({año})**\n"
                    f"⏱️ {dur} min | Termina: {fin.strftime('%H:%M')}\n\n"
                    f"{resumen[:250]}..."
                )
                
                btns = [[InlineKeyboardButton("▶️ Ver en Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")]]
                if trailer_url: btns.append([InlineKeyboardButton("📽️ Ver Trailer", url=trailer_url)])
                google_q = urllib.parse.quote(f"ver {orig} {año} online vose")
                btns.append([InlineKeyboardButton("🌐 Buscar VOSE / Web", url=f"https://www.google.com/search?q={google_q}")])

                if poster:
                    url_poster = f"https://image.tmdb.org/t/p/w500{poster}"
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=url_poster, caption=final_txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                    await espera.delete()
                    print("✅ Respuesta enviada con póster", flush=True)
                else:
                    await espera.edit_text(final_txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                return

        await espera.edit_text(txt)
    except Exception as e:
        print(f"🔥 ERROR CRÍTICO: {str(e)}", flush=True)
        await espera.edit_text(f"Hubo un desliz en la cava. (Error: {str(e)[:40]}...)")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("🚀 FRANCINE V35 - ACTIVANDO ESCÁNER...", flush=True)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.run_polling(drop_pending_updates=True)
