import os
import logging
import requests
import threading
from flask import Flask # Nueva pieza
import asyncio
import nest_asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- 0. SERVIDOR WEB PARA RENDER ---
# Esto engaña a Render para que crea que somos una web y nos deje correr gratis
web_app = Flask('')
@web_app.route('/')
def home(): return "Francine está despierta y cuidando la cava. 🍷"

def run_web():
    web_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- 1. CONFIGURACIÓN DEL BOT ---
nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

genai.configure(api_key=GEMINI_KEY)
modelo_ia = genai.GenerativeModel('gemini-1.5-flash')

# --- MOTOR DE BÚSQUEDA ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        q = query.strip()
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except: return None
    return None

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    prompt = f"Eres Francine, sommelier de cine argentina. Respondé corto. Etiqueta: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        response = modelo_ia.generate_content(prompt)
        txt = response.text
        if "[BUSCAR:" in txt:
            peli_buscada = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(peli_buscada)
            if peli:
                tit = peli.get('title'); imdb = peli.get('imdb_id')
                final_txt = f"{txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit}**"
                btns = [[InlineKeyboardButton("▶️ Ver en Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")]]
                await espera.edit_text(final_txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
            else: await espera.edit_text("❌ No encontré la ficha.")
        else: await espera.edit_text(txt)
    except Exception as e: await espera.edit_text(f"❌ Error: {e}")

# --- ARRANQUE ---
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    print("🚀 BOT DE TELEGRAM INICIADO")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Arrancamos el servidor web en un hilo y el bot en el principal
    threading.Thread(target=run_web).start()
    run_bot()
