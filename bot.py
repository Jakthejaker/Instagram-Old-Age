import os
import threading
import telebot
from flask import Flask

# Get Telegram Bot Token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set. Please add it in Render environment variables.")

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ================== TELEGRAM BOT HANDLERS ==================

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 Hello! Your bot is running successfully on Render!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"You said: {message.text}")

# ================== FLASK APP ==================

app = Flask(_name_)

@app.route("/")
def home():
    return "✅ Telegram Bot + Flask server running on Render!", 200

# ================== BACKGROUND BOT THREAD ==================

def run_bot():
    print("🚀 Telegram bot polling started...")
    bot.infinity_polling(timeout=60, long_polling_timeout = 60)

# ================== MAIN ==================

if _name_ == "_main_":
    # Start Telegram bot in background
    threading.Thread(target=run_bot, daemon=True).start()

    # Start Flask app (Render requires a web service)
    port = int(os.environ.get("PORT", 5000))
    print(f"🌍 Flask server running on port {port}...")
    app.run(host="0.0.0.0", port=port)
