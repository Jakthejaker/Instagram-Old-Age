import os
import threading
import telebot
from flask import Flask

# ====== ENV & BOT ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set. Please add it in Render environment variables.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ====== TELEGRAM HANDLERS ======
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 Hello! Your bot is running successfully on Render!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"You said: {message.text}")

# ====== FLASK APP ======
app = Flask(__name__)  
@app.route("/")
def home():
    return "✅ Telegram Bot + Flask server running on Render!", 200

@app.route("/healthz")
def health():
    return "ok", 200

# ====== BACKGROUND POLLING THREAD ======
_bot_thread_started = False
_bot_thread = None

def run_bot():
    print("🚀 Telegram bot polling started...")
    # Keep timeouts modest so Gunicorn shutdowns are graceful
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

def ensure_bot_thread():
    global _bot_thread_started, _bot_thread
    if not _bot_thread_started:
        _bot_thread = threading.Thread(target=run_bot, daemon=True, name="telebot-poller")
        _bot_thread.start()
        _bot_thread_started = True
        print("🧵 TeleBot thread started")

# Start the bot thread on module import so it works under Gunicorn (render runs: gunicorn bot:app)
ensure_bot_thread()

# ====== LOCAL DEV ENTRYPOINT (ignored on Render/Gunicorn) ======
if _name_ == "_main_":
    # When running locally: starts Flask dev server
    port = int(os.environ.get("PORT", 5000))
    print(f"🌍 Flask server running on port {port}...")
    app.run(host="0.0.0.0", port=port)

