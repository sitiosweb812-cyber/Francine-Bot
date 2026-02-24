import os, logging, requests, threading, urllib.parse, pytz, time
from flask import Flask
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- 1. CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
def log_info(msg):
    print(f"FRANCINE_LOG: {msg}", flush=True)

# Variables de entorno
TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
PORT = int(os.environ.get("PORT", 8080)) # El puerto que Render exige

# Configuración IA
genai.configure(api_key=GEMINI_KEY)

# --- 2. SERVIDOR WEB (Prioridad #1 para Render) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Francine V40: Puerta abierta y cava lista. 🍷", 200

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
    log_info(f"Mensaje recibido: {update.message.text}")
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    
    try:
        # Selección automática de modelo
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in models else models[0]
        model = genai.GenerativeModel(target)
        
        prompt = f"Sos Francine, sommelier de cine argentina. Respondé en 2 frases. Etiqueta: [BUSCAR: Titulo Original]. Pedido: {update.message.text}"
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
        log_info(f"Error: {e}")
        await espera.edit_text("Hubo un desliz en la cava. Reintentá.")

# --- 4. ARRANQUE MAESTRO ---
def run_bot():
    try:
        log_info("🧹 Limpiando conexiones viejas...")
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
        time.sleep(2)
        
        log_info("🚀 Lanzando Francine...")
        application = Application.builder().token(TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        log_info(f"Falla crítica en el bot: {e}")

if __name__ == "__main__":
    # PASO 1: Lanzamos el bot en un hilo separado
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # PASO 2: Abrimos el puerto inmediatamente para Render
    log_info(f"📢 Abriendo puerto {PORT}...")
    web_app.run(host='0.0.0.0', port=PORT)
