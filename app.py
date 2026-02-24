import os, logging, requests, urllib.parse, pytz
from flask import Flask, request
from datetime import datetime, timedelta
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURACIÓN DE ALTO NIVEL ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TMDB_KEY = os.environ.get('TMDB_KEY', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
# Render nos da automáticamente la URL externa
RENDER_URL = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'francine-bot.onrender.com')

# Configuración IA
genai.configure(api_key=GEMINI_KEY)

# --- SERVIDOR WEB (Flask manejará todo) ---
app = Flask(__name__)

# Inicializamos la Aplicación de Telegram (sin arrancarla como polling)
ptb_app = Application.builder().token(TOKEN).build()

# --- LÓGICA DE DATOS ---
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
        logger.error(f"Error TMDB: {e}")
    return None

def get_model():
    # Selección dinámica para evitar el error 404 de raíz
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for target in ['models/gemini-1.5-flash', 'models/gemini-pro']:
            if target in models: return genai.GenerativeModel(target)
        return genai.GenerativeModel(models[0])
    except: return genai.GenerativeModel('gemini-1.5-flash')

# --- MANEJADOR DE MENSAJES ---
async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    espera = await update.message.reply_text("🍷 Francine está eligiendo...")
    
    try:
        model = get_model()
        prompt = f"Sos Francine, sommelier de cine argentina. Respondé corto (2 frases). Etiqueta obligatoria: [BUSCAR: Titulo Original]. Pedido: {update.message.text}"
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
        logger.error(f"Error: {e}")
        await espera.edit_text("Hubo un desliz en la cava. Reintentá.")

# --- RUTAS DEL SERVIDOR ---
@app.route('/')
def index(): return "Francine V38 Webhook Active 🍷", 200

@app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    # Recibimos la actualización de Telegram
    update = Update.de_json(request.get_json(force=True), ptb_app.bot)
    # La procesamos
    await ptb_app.process_update(update)
    return 'OK', 200

# Registro de manejadores
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))

# Configuración del Webhook al arrancar
async def setup_webhook():
    webhook_url = f"https://{RENDER_URL}/{TOKEN}"
    logger.info(f"🛰️ Seteando Webhook en: {webhook_url}")
    # Esto le dice a Telegram: "Olvidate de Polling, mandame todo acá"
    await ptb_app.bot.set_webhook(url=webhook_url)
    # Inicializamos la app interna para que esté lista
    await ptb_app.initialize()

# Corremos la configuración inicial antes de que Flask tome el mando
import asyncio
loop = asyncio.get_event_loop()
loop.run_until_complete(setup_webhook())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
