import os
import logging
import threading
from flask import Flask
import telebot

# ===============================
# 🔧 Config
# ===============================
TOKEN = os.environ.get("BOT_TOKEN")  # set this in Render environment variables
ADMIN_ID = os.environ.get("ADMIN_ID")  # optional, your Telegram ID for error reports

bot = telebot.TeleBot(TOKEN)

# ===============================
# 📜 Logging setup
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===============================
# 🤖 Telegram Bot Handlers
# ===============================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    bot.reply_to(message, "👋 Hello! Your bot is alive and running on Render 🚀")


@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.reply_to(message, f"🔁 You said: {message.text}")


# ===============================
# 🌍 Flask Web App (for Render + UptimeRobot)
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Telegram Bot is running on Render"

@app.route("/ping-test")
def ping_test():
    return "Bot is alive 🚀"


# ===============================
# 🔄 Run Bot in Background Thread
# ===============================
def run_bot():
    logging.info("Starting Telegram bot polling...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout = 30)
        except Exception as e:
            logging.error(f"Bot crashed with error: {e}")
            if ADMIN_ID:
                try:
                    bot.send_message(ADMIN_ID, f"⚠ Bot crashed: {e}")
                except:
                    pass
            # small sleep before retry
            import time
            time.sleep(5)


threading.Thread(target=run_bot, daemon=True).start()


# ===============================
# 🚀 Flask App Runner
# ===============================
if _name_ == "_main_":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port)

