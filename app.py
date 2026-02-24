import os
import logging
import requests
import threading
from flask import Flask
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

# --- 1. SERVIDOR WEB (Health Check) ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Francine está lista. 🍷", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- 2. MOTOR DE BÚSQUEDA ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except: return None
    return None

# --- 3. LÓGICA DE IA DINÁMICA ---
def obtener_modelo():
    """Busca el mejor modelo disponible para evitar el error 404"""
    try:
        modelos_disponibles = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Prioridad: flash 1.5, luego pro, luego lo que haya
        for m in ['models/gemini-1.5-flash', 'models/gemini-pro', 'models/gemini-1.0-pro']:
            if m in modelos_disponibles:
                logger.info(f"✅ Usando modelo: {m}")
                return genai.GenerativeModel(m)
        return genai.GenerativeModel(modelos_disponibles[0])
    except Exception as e:
        logger.error(f"❌ Error buscando modelos: {e}")
        return genai.GenerativeModel('gemini-1.5-flash')

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    prompt = f"Sos Francine, sommelier de cine argentina. Recomendá una peli corta. Etiqueta: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        model = obtener_modelo()
        response = model.generate_content(prompt)
        txt = response.text
        
        if "[BUSCAR:" in txt:
            peli_buscada = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(peli_buscada)
            if peli:
                tit = peli.get('title'); imdb = peli.get('imdb_id')
                final_txt = f"{txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit}**"
                btn = [[InlineKeyboardButton("▶️ Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")]]
                await espera.edit_text(final_txt, reply_markup=InlineKeyboardMarkup(btn), parse_mode='Markdown')
                return
        await espera.edit_text(txt)
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")
        await espera.edit_text(f"Hubo un tema en la cava: {str(e)[:50]}")

# --- 4. ARRANQUE ---
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("🚀 FRANCINE V33 - INICIANDO...", flush=True)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    application.run_polling(drop_pending_updates=True)
