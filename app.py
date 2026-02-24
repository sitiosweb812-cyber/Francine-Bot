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

# --- 0. CONFIGURACIÓN ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

genai.configure(api_key=GEMINI_KEY)

# --- 1. SERVIDOR WEB ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Francine está elegante y lista. 🍷", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- 2. MOTOR TMDB MEJORADO (Trae videos y duración) ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            # Pedimos detalles completos, incluyendo videos
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", 
                               params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, 
                               timeout=10).json()
    except: return None
    return None

# --- 3. LÓGICA DE IA ---
def obtener_modelo():
    try:
        modelos_disponibles = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in ['models/gemini-1.5-flash', 'models/gemini-pro']:
            if m in modelos_disponibles: return genai.GenerativeModel(m)
        return genai.GenerativeModel(modelos_disponibles[0])
    except: return genai.GenerativeModel('gemini-1.5-flash')

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    espera = await update.message.reply_text("🍷 Francine está eligiendo el maridaje...")
    
    # Prompt estricto para evitar el "choclo" de texto
    prompt = f"Sos Francine, sommelier de cine argentina. Respondé en máximo 2 frases cortas y con mucha onda. RECOMENDÁ UNA PELÍCULA. Etiqueta obligatoria: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        model = obtener_modelo()
        response = model.generate_content(prompt)
        txt = response.text
        
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
                
                # Calcular hora de fin (Argentina)
                zona = pytz.timezone('America/Argentina/Buenos_Aires')
                ahora = datetime.now(zona)
                fin = ahora + timedelta(minutes=dur) if dur else ahora
                
                # Buscar Trailer en YouTube
                trailer_url = None
                for v in peli.get('videos', {}).get('results', []):
                    if v['site'] == 'YouTube' and v['type'] == 'Trailer':
                        trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
                        break

                # Formatear el mensaje final
                cuerpo = txt.split("[BUSCAR:")[0].strip()
                final_txt = (
                    f"🍷 {cuerpo}\n\n"
                    f"🎬 **{tit} ({año})**\n"
                    f"⏱️ {dur} min | Termina: {fin.strftime('%H:%M')}\n\n"
                    f"{resumen[:250]}..."
                )
                
                # Botones
                btns = []
                stremio_url = f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}"
                btns.append([InlineKeyboardButton("▶️ Ver en Stremio", url=stremio_url)])
                
                if trailer_url:
                    btns.append([InlineKeyboardButton("📽️ Ver Trailer", url=trailer_url)])
                
                google_q = urllib.parse.quote(f"ver {orig} {año} online vose")
                btns.append([InlineKeyboardButton("🌐 Buscar VOSE / Web", url=f"https://www.google.com/search?q={google_q}")])

                # Enviar póster si existe, sino solo texto
                if poster:
                    url_poster = f"https://image.tmdb.org/t/p/w500{poster}"
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=url_poster,
                        caption=final_txt,
                        reply_markup=InlineKeyboardMarkup(btns),
                        parse_mode='Markdown'
                    )
                    await espera.delete()
                else:
                    await espera.edit_text(final_txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                return

        await espera.edit_text(txt)
    except Exception as e:
        logger.error(f"Error: {e}")
        await espera.edit_text("Hubo un desliz en la cava. Reintentá.")

# --- 4. ARRANQUE ---
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("🚀 FRANCINE V34 - MODO GALA...", flush=True)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.run_polling(drop_pending_updates=True)
