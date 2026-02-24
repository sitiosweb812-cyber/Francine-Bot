import os
import logging
import requests
import sqlite3
import pytz
import asyncio
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURACIÓN ---
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

genai.configure(api_key=GEMINI_KEY)
modelo_ia = genai.GenerativeModel('gemini-1.5-flash')

# Base de datos
archivo_db = 'peliculas_vistas.db'
def init_db():
    conn = sqlite3.connect(archivo_db)
    conn.execute('CREATE TABLE IF NOT EXISTS peliculas_vistas (id_tmdb INTEGER PRIMARY KEY, titulo TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.close()
init_db()

# --- MOTOR DE BÚSQUEDA ---
def buscar_en_tmdb(query):
    url = "https://api.themoviedb.org/3/search/movie"
    try:
        q = query.strip().replace('"', '').replace("'", "")
        res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if not res.get('results'):
            res = requests.get(url, params={'api_key': TMDB_KEY, 'query': q.split()[0], 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except: return None
    return None

# --- MANEJADORES ---
async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_txt = update.message.text
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    prompt = f"Eres Francine, sommelier de cine argentina. Respondé en 2 frases máximo con mucha onda. Etiqueta final: [BUSCAR: Titulo Original]. Pedido: {user_txt}"
    
    try:
        response = modelo_ia.generate_content(prompt)
        txt = response.text
        if "[BUSCAR:" in txt:
            peli_buscada = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(peli_buscada)
            if peli:
                tit = peli.get('title'); orig = peli.get('original_title', tit); año = peli.get('release_date', '????')[:4]
                imdb = peli.get('imdb_id')
                final_txt = f"{txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit} ({año})**"
                btns = [[InlineKeyboardButton("▶️ Ver en Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")]]
                btns.append([InlineKeyboardButton("🌐 Ver VOSE", url=f"https://www.google.com/search?q={urllib.parse.quote(f'ver {orig} {año} online vose')}")])
                await update.message.reply_text(final_txt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(btns))
                await context.bot.delete_message(update.message.chat_id, espera.message_id)
            else:
                await espera.edit_text("❌ No encontré la ficha.")
        else:
            await espera.edit_text(txt)
    except Exception as e:
        await espera.edit_text(f"❌ Error: {e}")

# --- ARRANQUE ---
if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    print("🚀 FRANCINE ONLINE")
    application.run_polling(drop_pending_updates=True)
