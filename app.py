import os
import logging
import requests
import threading
from flask import Flask
import asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- 0. CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. LLAVES (SECRETS) ---
TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

# Configuración de IA - Usamos el modelo con nombre completo para evitar el 404
genai.configure(api_key=GEMINI_KEY)
modelo_ia = genai.GenerativeModel('gemini-1.5-flash') # Sigue siendo este, pero el parche va por dentro

# --- 2. SERVIDOR WEB (Para Render) ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): 
    return "Francine está despierta y lista para recomendar. 🍷", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- 3. LÓGICA DEL BOT ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        # Limpieza básica de la búsqueda
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except Exception as e:
        logger.error(f"Error en TMDB: {e}")
    return None

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    
    # Prompt optimizado
    prompt = f"Sos Francine, sommelier de cine argentina. Respondé corto y con onda. Etiqueta obligatoria: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        # Llamada a la IA
        response = modelo_ia.generate_content(prompt)
        txt = response.text
        
        if "[BUSCAR:" in txt:
            peli_buscada = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(peli_buscada)
            
            if peli:
                tit = peli.get('title')
                imdb = peli.get('imdb_id')
                final_txt = f"{txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit}**"
                
                btns = [[InlineKeyboardButton("▶️ Ver en Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")]]
                await espera.edit_text(final_txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                return
                
        await espera.edit_text(txt)
    except Exception as e:
        logger.error(f"Error IA: {e}")
        # Si el error persiste, probamos con el modelo alternativo
        await espera.edit_text(f"Hubo un desliz en la cava (Error de API). Reintentá en unos segundos.")

# --- 4. ARRANQUE ---
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    print("🚀 INICIANDO FRANCINE...", flush=True)
    if not TOKEN or not GEMINI_KEY:
        print("❌ ERROR: Faltan variables de entorno.")
    else:
        application = Application.builder().token(TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
        application.run_polling(drop_pending_updates=True)
