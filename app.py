import os, logging, requests, threading, urllib.parse, pytz, time
from flask import Flask
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# --- CONFIGURACIÓN DE NIVEL EXPERTO ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

# Inicialización de Google
genai.configure(api_key=GEMINI_KEY)

# --- SERVIDOR WEB (Health Check) ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Francine Engine V37: Active", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- LÓGICA DE DATOS ---
def buscar_en_tmdb(query):
    try:
        q = query.replace("[BUSCAR:", "").replace("]", "").strip()
        search_url = "https://api.themoviedb.org/3/search/movie"
        res = requests.get(search_url, params={'api_key': TMDB_KEY, 'query': q, 'language': 'es-AR'}, timeout=10).json()
        if res.get('results'):
            m_id = res['results'][0]['id']
            return requests.get(f"https://api.themoviedb.org/3/movie/{m_id}", 
                               params={'api_key': TMDB_KEY, 'language': 'es-AR', 'append_to_response': 'videos'}, timeout=10).json()
    except Exception as e:
        logger.error(f"Error en TMDB: {e}")
    return None

# --- SELECTOR DINÁMICO DE MODELO (Evita el 404) ---
def get_best_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Buscamos por prioridad
        for target in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']:
            if target in models:
                logger.info(f"🚀 Motor IA seleccionado: {target}")
                return genai.GenerativeModel(target)
        return genai.GenerativeModel(models[0])
    except Exception as e:
        logger.error(f"Error seleccionando modelo: {e}")
        return genai.GenerativeModel('gemini-1.5-flash')

# --- MANEJADOR DE MENSAJES ---
async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    espera = await update.message.reply_text("🍷 Francine está eligiendo el maridaje...")
    
    try:
        model = get_best_model()
        prompt = (f"Sos Francine, sommelier de cine argentina. Recomendá una peli corta basándote en: {update.message.text}. "
                  "Respondé en 2 frases máximo. Obligatorio incluir al final: [BUSCAR: Titulo Original].")
        
        response = model.generate_content(prompt)
        txt = response.text
        
        if "[BUSCAR:" in txt:
            p_query = txt.split("[BUSCAR:")[1].split("]")[0].strip()
            peli = buscar_en_tmdb(p_query)
            
            if peli:
                tit = peli.get('title'); orig = peli.get('original_title', tit)
                año = peli.get('release_date', '????')[:4]; dur = peli.get('runtime', 0)
                imdb = peli.get('imdb_id'); poster = peli.get('poster_path')
                
                # Hora de finalización (Argentina)
                fin = datetime.now(pytz.timezone('America/Argentina/Buenos_Aires')) + timedelta(minutes=dur)
                
                # Construcción de respuesta
                cap = f"🍷 {txt.split('[BUSCAR:')[0].strip()}\n\n🎬 **{tit} ({año})**\n⏱️ {dur} min | Termina: {fin.strftime('%H:%M')}"
                
                btns = [
                    [InlineKeyboardButton("▶️ Ver en Stremio", url=f"https://web.stremio.com/#/detail/movie/{imdb}/{imdb}")],
                    [InlineKeyboardButton("🌐 Buscar VOSE / Web", url=f"https://www.google.com/search?q={urllib.parse.quote(f'ver {orig} {año} online vose')}")]
                ]

                if poster:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f"https://image.tmdb.org/t/p/w500{poster}", 
                                               caption=cap, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                    await espera.delete()
                else:
                    await espera.edit_text(cap, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
                return

        await espera.edit_text(txt)
        
    except Exception as e:
        logger.error(f"Error crítico en proceso: {e}")
        await espera.edit_text("Hubo un desliz en la cava. Reintentá en un momento.")

# --- ARRANQUE CON REINTENTO AUTOMÁTICO ---
def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    while True:
        try:
            logger.info("📡 Conectando Francine a Telegram...")
            app = Application.builder().token(TOKEN).build()
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
            
            # drop_pending_updates=True limpia los mensajes acumulados mientras el bot estuvo off
            app.run_polling(drop_pending_updates=True, close_loop=False)
            
        except Conflict:
            logger.warning("⚠️ Conflicto detectado. Otra instancia está activa. Reintentando en 10s...")
            time.sleep(10)
        except Exception as e:
            logger.error(f"💥 Error inesperado: {e}. Reiniciando...")
            time.sleep(5)

if __name__ == "__main__":
    main()
