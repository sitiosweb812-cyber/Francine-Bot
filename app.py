import os, logging, requests, threading, urllib.parse, pytz, time, asyncio
from flask import Flask
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# --- 1. CONFIGURACIÓN ---
logging.basicConfig(level=logging.INFO)
def log_info(msg):
    print(f"FRANCINE_LOG: {msg}", flush=True)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
PORT = int(os.environ.get("PORT", 8080))

genai.configure(api_key=GEMINI_KEY)

# --- 2. SERVIDOR WEB (Intacto para Render) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Francine V44: Modo Cirujano (1.5 Flash Forzado). 🍷", 200

# --- 3. LÓGICA DEL BOT ---
def buscar_en_tmdb(query):
    try:
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        res = requests.get("https://api.themoviedb.org/3/search/movie", 
                           params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", 
                               params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except Exception as e:
        log_info(f"Error TMDB: {e}")
    return None

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    log_info(f"Mensaje de usuario: {update.message.text}")
    espera = await update.message.reply_text("🍷 Francine está buscando en la cava...")
    
    try:
        # --- LA INCISIÓN: FORZAMOS EL 1.5 FLASH MANUALMENTE ---
        # Borramos la búsqueda automática. Le exigimos este modelo exacto para tener 1500 peticiones.
        model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ])
        
        prompt = f"Sos Francine, sommelier de cine argentina. Respondé en 2 frases cortas. Etiqueta: [BUSCAR: Titulo Original]. Pedido: {update.message.text}"
        response = model.generate_content(prompt)
        txt = response.text
        
        if "[BUSCAR:" in txt:
            p_query = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(p_query)
            if peli:
                tit = peli.get('title'); orig = peli.get('original_title', tit)
                año = peli.get('release_date', '????')[:4]; dur = peli.get('runtime', 0)
                imdb = peli.get('imdb_id'); poster = peli.get('poster_path')
                
                fin = datetime.now(pytz.timezone('America/Argentina/Buenos_Aires')) + timedelta(minutes=dur)
                cap = f"🍷 {txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit} ({año})**\n⏱️ {dur} min | Termina: {fin.strftime('%H:%M')}"
                
                btns = [[InlineKeyboardButton("▶️ Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")],
                        [InlineKeyboardButton("🌐 Buscar VOSE", url=f"https://www.google.com/search?q={urllib.parse.quote(f'ver {orig} {año} online vose')}")]]

                if poster:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f"https://image.tmdb.org/t/p/w500{poster}", 
                                               caption=cap, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                    await espera.delete()
                else:
                    await espera.edit_text(cap, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                return
        await espera.edit_text(txt)
    except Exception as e:
        log_info(f"Error IA: {e}")
        await espera.edit_text("Hubo un desliz en la cava (Cupo de IA lleno o error temporal). Reintentá más tarde.")

# --- 4. ARRANQUE DEL BOT (ESCUDO ANTI-CONFLICTOS INTACTO) ---
def run_bot():
    log_info("🧹 Limpiando conexiones viejas...")
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except: pass
    time.sleep(2)
    
    asyncio.set_event_loop(asyncio.new_event_loop())
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    
    while True:
        try:
            log_info("🚀 Lanzando Francine V44 (Modo Cirujano)...")
            application.run_polling(drop_pending_updates=True, stop_signals=())
        except Conflict:
            log_info("⚠️ Fantasma de Telegram detectado (Conflict). Esperando 10s para reintentar...")
            time.sleep(10)
        except Exception as e:
            log_info(f"Falla en el bot: {e}. Reintentando en 5s...")
            time.sleep(5)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    log_info(f"📢 Abriendo puerto {PORT}...")
    web_app.run(host='0.0.0.0', port=PORT)
