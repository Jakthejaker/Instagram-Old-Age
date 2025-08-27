import sqlite3
import telebot
from telebot import types
import time
import os
from flask import Flask, request
import threading
import atexit

app = Flask(__name__)

# ================== CONFIG ==================
# Get values from environment variables with fallbacks
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8201178560:AAGPx4o8teYXFt3ewDJ0IF3kSKEDIuaLYao")
ADMIN_IDS = os.environ.get('ADMINS', "8048054789,2115677414")
ADMINS = [int(x.strip()) for x in ADMIN_IDS.split(",")]

# 🔹 Channels required to join
CHANNELS = [
    {"id": "@jak_paradise", "url": "https://t.me/jak_paradise"},
    {"id": "-1002408750694", "url": "https://t.me/+tU7esamIk45jZTg0"},
    {"id": "-1002964116333", "url": "https://t.me/+yOTZqVq194s0OTk0"},  # Main channel
    {"id": "-1002793343378", "url": "https://t.me/+frT0WdQQPwQ1YzY0"}   # New channel added
]
CHANNEL_ID_FOR_REF = -1002964116333  # Channel for referral & withdrawal messages

# Init bot (single-threaded to keep sqlite happy)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Database path - use a persistent location
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

# ================== DATABASE ==================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        referred_by INTEGER,
        last_bonus INTEGER DEFAULT 0
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reward TEXT
    )""")
    conn.commit()
    conn.close()

# Initialize database
init_db()

# ================== HELPERS ==================
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def send_to_admins(text: str, parse_mode: str = None):
    for admin_id in ADMINS:
        try:
            bot.send_message(admin_id, text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

def format_user_info(user):
    name = user.first_name or ""
    uname = f"@{user.username}" if user.username else "❌ No Username"
    return f"•🥂 Name:- {name} • 🎀\nUsername :- {uname} 💎\nID: {user.id} ☠"

def add_user(user_id, username, ref_id=None, user=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                       (user_id, username, ref_id))
        conn.commit()

        # 🔔 New user info to admins
        if user:
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            new_user_msg = f"🔔 New user started the bot:\nTotal :- {total_users}\n{format_user_info(user)}"
            send_to_admins(new_user_msg)

        # 🔔 Referral handling
        if ref_id:
            cursor.execute("UPDATE users SET balance = balance + 3 WHERE user_id=?", (ref_id,))
            conn.commit()
            try:
                bot.send_message(ref_id, "🎉 You earned +3 💎 Diamonds (Referral Bonus)!")
            except Exception as e:
                print(f"Failed to notify referrer {ref_id}: {e}")

            # Referrer username
            cursor.execute("SELECT username FROM users WHERE user_id=?", (ref_id,))
            referrer = cursor.fetchone()
            ref_username = f"@{referrer[0]}" if referrer and referrer[0] else "❌ No Username"

            if user:
                ref_msg = f"🔔 Referral by {ref_username}:\n{format_user_info(user)}"
                send_to_admins(ref_msg)
    
    conn.close()

def get_balance(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def _normalize_chat_id(chat_id_field):
    """
    Accepts username like '@channel' or numeric as string '-100...' or int.
    Returns a value suitable for get_chat_member.
    """
    if isinstance(chat_id_field, int):
        return chat_id_field
    if isinstance(chat_id_field, str):
        if chat_id_field.startswith('@'):
            return chat_id_field
        try:
            return int(chat_id_field)
        except:
            return chat_id_field
    return chat_id_field

def check_subscription(user_id):
    for ch in CHANNELS:
        chat_id = _normalize_chat_id(ch["id"])
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            print(f"Subscription check failed for {ch['id']}: {e}")
            return False
    return True

def send_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💎 Balance", "👥 Referral Link")
    markup.add("🎁 Bonus", "⚡ Withdraw")
    markup.add("🆘 Support")
    bot.send_message(user_id, "✨ Welcome to the Bot Menu 👇", reply_markup=markup)

def send_join_prompt(user_id):
    markup = types.InlineKeyboardMarkup()
    for ch in CHANNELS:
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=ch["url"]))
    markup.add(types.InlineKeyboardButton("✅ I Joined", callback_data="check_subs"))
    text = (
        "🚀 <b>Welcome to Insta Old Age Bot</b>\n\n"
        "🔒 To continue, please <b>join all channels</b> below:\n\n"
        "👉 After joining, press the <b>✅ I Joined</b> button."
    )
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML")

# ================== START / JOIN FLOW ==================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()
    ref_id = None
    if len(args) > 1:
        try:
            ref_id = int(args[1])
        except:
            ref_id = None

    add_user(user_id, username, ref_id, message.from_user)

    if check_subscription(user_id):
        send_main_menu(user_id)
    else:
        send_join_prompt(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def callback_check(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        try:
            bot.edit_message_text("✅ Thank you for joining! Now you can use the bot freely.",
                                  chat_id=call.message.chat.id,
                                  message_id=call.message.message_id)
        except:
            pass
        send_main_menu(user_id)
    else:
        bot.answer_callback_query(call.id, "❌ Please join all required channels first!")

# ================== ADMIN: STOCK COMMANDS ==================
@bot.message_handler(commands=['addstock'])
def add_stock(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Sorry, only admin can use this command! 💎")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Usage: /addstock Reward Text\nExample: /addstock 🎁 1000 Coins")
        return
    reward_text = args[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stock (reward) VALUES (?)", (reward_text,))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Stock added:\n{reward_text}")

@bot.message_handler(commands=['checkstock'])
def check_stock(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Sorry, only admin can use this command! 💎")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM stock")
    count = cursor.fetchone()[0]
    conn.close()
    bot.reply_to(message, f"📦 Current stock count: {count} item(s)")

@bot.message_handler(commands=['stocklist'])
def stock_list(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Sorry, only admin can use this command! 💎")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, reward FROM stock")
    items = cursor.fetchall()
    conn.close()
    if not items:
        bot.reply_to(message, "📦 Stock is empty.")
        return
    text = "📦 Current Stock Items:\n\n"
    for stock_id, reward in items:
        text += f"ID: {stock_id} | Reward: {reward}\n"
    bot.reply_to(message, text)

# ================== ADMIN: UNIVERSAL BROADCAST ==================
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Sorry, only admins can use this command! 💎")
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        # Direct text broadcast via resend mode
        broadcast_text = args[1]
        send_broadcast_text(message.from_user.id, broadcast_text)
    else:
        # Ask for mode
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Forward Mode", callback_data="broadcast_forward"))
        markup.add(types.InlineKeyboardButton("📝 Resend Mode", callback_data="broadcast_resend"))
        bot.send_message(message.chat.id, "📢 Choose broadcast mode:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["broadcast_forward", "broadcast_resend"])
def choose_broadcast_mode(call):
    if not is_admin(call.from_user.id):
        return

    mode = "forward" if call.data == "broadcast_forward" else "resend"
    msg = bot.send_message(call.message.chat.id, "📩 Please send the content (text/photo/video/document/audio/voice/sticker/GIF) you want to broadcast.")
    bot.register_next_step_handler(msg, lambda m: process_broadcast(m, mode))

def process_broadcast(message, mode):
    if not is_admin(message.from_user.id):
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    total_users = len(users)

    sent = 0
    failed = 0
    errors = []

    for user in users:
        uid = user[0]
        try:
            if mode == "forward":
                bot.forward_message(uid, message.chat.id, message.message_id)

            elif mode == "resend":
                ct = message.content_type
                if ct == "text":
                    bot.send_message(uid, f"📢 <b>Admin Message:</b>\n\n{message.text}", parse_mode="HTML")
                elif ct == "photo":
                    bot.send_photo(uid, message.photo[-1].file_id,
                                   caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "video":
                    bot.send_video(uid, message.video.file_id,
                                   caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "document":
                    bot.send_document(uid, message.document.file_id,
                                      caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "voice":
                    bot.send_voice(uid, message.voice.file_id,
                                   caption=f"📢 Admin Message:\n\n{message.caption or ''}")
                elif ct == "audio":
                    bot.send_audio(uid, message.audio.file_id,
                                   caption=f"📢 Admin Message:\n\n{message.caption or ''}")
                elif ct == "sticker":
                    bot.send_sticker(uid, message.sticker.file_id)
                elif ct == "animation":  # GIF
                    bot.send_animation(uid, message.animation.file_id,
                                       caption=f"📢 Admin Message:\n\n{message.caption or ''}")
                else:
                    bot.send_message(uid, "📢 Admin sent an update (unsupported media type).")

            sent += 1
        except Exception as e:
            failed += 1
            errors.append(f"User {uid}: {e}")
        finally:
            # Tiny delay to be gentle with rate limits
            time.sleep(0.03)

    # 📊 Final Report to initiating admin
    report = (
        "📢 <b>Broadcast Status</b>\n\n"
        f"👥 Total Users in Bot: <b>{total_users}</b>\n"
        f"📩 Messages Sent: <b>{sent}</b>\n"
        f"❌ Failed to Send: <b>{failed}</b>\n"
    )
    if errors:
        sample = "\n".join(errors[:5])
        report += f"\n⚠ Errors (sample):\n{sample}"

    bot.send_message(message.from_user.id, report, parse_mode="HTML")

def send_broadcast_text(admin_id, text):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    total_users = len(users)

    sent = 0
    failed = 0
    errors = []

    for user in users:
        uid = user[0]
        try:
            bot.send_message(uid, f"📢 <b>Admin Message:</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            errors.append(f"User {uid}: {e}")
        finally:
            time.sleep(0.03)

    report = (
        "📢 <b>Broadcast Status</b>\n\n"
        f"👥 Total Users in Bot: <b>{total_users}</b>\n"
        f"📩 Messages Sent: <b>{sent}</b>\n"
        f"❌ Failed to Send: <b>{failed}</b>\n"
    )
    if errors:
        sample = "\n".join(errors[:5])
        report += f"\n⚠ Errors (sample):\n{sample}"

    bot.send_message(admin_id, report, parse_mode="HTML")

# ================== USER MENU ==================
@bot.message_handler(func=lambda message: True)
def menu_handler(message):
    user_id = message.from_user.id
    txt = message.text

    if txt == "💎 Balance":
        bal = get_balance(user_id)
        bot.send_message(user_id, f"💎 Your Balance: {bal} Diamonds")

    elif txt == "👥 Referral Link":
        link = f"https://t.me/{bot.get_me().username}?start={user_id}"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,))
        refs = cursor.fetchone()[0]
        conn.close()
        bot.send_message(user_id, f"🔗 Your referral link:\n{link}\n\n👥 Referrals: {refs}\n💎 Per Referral: 3 Diamonds")

    elif txt == "🎁 Bonus":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT last_bonus FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        last_bonus = row[0] if row else 0
        now = int(time.time())
        if now - last_bonus >= 86400:
            update_balance(user_id, 2)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_bonus=? WHERE user_id=?", (now, user_id))
            conn.commit()
            conn.close()
            bot.send_message(user_id, "🎁 You received +2 💎 Diamonds (Daily Bonus)!")
        else:
            remaining = 86400 - (now - last_bonus)
            hrs = remaining // 3600
            mins = (remaining % 3600) // 60
            bot.send_message(user_id, f"⏳ Bonus already claimed! Try again in {hrs}h {mins}m.")

    elif txt == "⚡ Withdraw":
        bal = get_balance(user_id)
        if bal >= 7:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirm", callback_data="withdraw_confirm"))
            bot.send_message(
                user_id,
                f"💎 Your Balance: {bal} Diamonds\n\n⚠ 7 Diamonds are required to withdraw.\n\n👉 Do you want to exchange 7 Diamonds for a reward?",
                reply_markup=markup
            )
        else:
            bot.send_message(user_id, f"❌ You need at least 7 💎 Diamonds to withdraw. You have {bal}.")

    elif txt == "🆘 Support":
        bot.send_message(user_id, "📩 For help, contact admin: @Jakhelper_bot")

    else:
        # If user hasn't joined, keep nudging them
        if not check_subscription(user_id):
            send_join_prompt(user_id)
            return
        bot.send_message(user_id, "❓ Unknown command. Use the menu buttons.")

# ================== WITHDRAW FLOW ==================
@bot.callback_query_handler(func=lambda call: call.data == "withdraw_confirm")
def confirm_withdraw(call):
    user_id = call.from_user.id
    bal = get_balance(user_id)
    if bal >= 7:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, reward FROM stock ORDER BY id LIMIT 1")
        stock_item = cursor.fetchone()
        if stock_item:
            stock_id, reward_text = stock_item
            cursor.execute("DELETE FROM stock WHERE id=?", (stock_id,))
            update_balance(user_id, -7)
            conn.commit()
            conn.close()

            # Send the reward from stock to the user
            bot.send_message(user_id, reward_text)

            # Notify channel and all admins (no hearts)
            try:
                bot_username = bot.get_me().username
            except:
                bot_username = "your_bot"

            withdraw_msg = (
                "💎 Request for withdrawal of 7 Diamonds created successfully!\n\n"
                f"User: @{call.from_user.username}\n\n"
                f"Bot :- @{bot_username}"
            )
            try:
                bot.send_message(CHANNEL_ID_FOR_REF, withdraw_msg)
            except Exception as e:
                print(f"Failed to notify channel: {e}")
            send_to_admins(withdraw_msg)
        else:
            bot.send_message(user_id, "❌ Sorry, stock is empty. We will add soon 😔 To talk with admin message here 📩 @Jakhelper_bot")
    else:
        bot.send_message(user_id, "❌ You don't have enough Diamonds.")

# ================== WEBHOOK SETUP ==================
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
WEBHOOK_PATH = f'/{BOT_TOKEN}'

@app.route('/')
def index():
    return 'Bot is running!'

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 403

# ================== BACKGROUND POLLING THREAD ==================
_bot_thread_started = False
_bot_thread = None

def run_bot():
    print("🚀 Telegram bot polling started...")
    try:
        # Keep timeouts modest so Gunicorn shutdowns are graceful
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot polling error: {e}")
        # Try to restart the bot thread after a delay
        time.sleep(10)
        ensure_bot_thread()

def ensure_bot_thread():
    global _bot_thread_started, _bot_thread
    if not _bot_thread_started:
        # Only start the bot in the main process, not in Gunicorn workers
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and not os.environ.get('GUNICORN_WORKER_CLASS'):
            _bot_thread = threading.Thread(target=run_bot, daemon=True, name="telebot-poller")
            _bot_thread.start()
            _bot_thread_started = True
            print("🧵 TeleBot thread started")
        else:
            print("⚠️  Not starting bot in Gunicorn worker process")

# Cleanup function to stop the bot properly
def stop_bot():
    print("🛑 Stopping bot...")
    try:
        bot.stop_polling()
    except:
        pass

# Register cleanup function
atexit.register(stop_bot)

# Start the bot thread only if not running in a Gunicorn worker
ensure_bot_thread()

# ================== LOCAL DEV ENTRYPOINT ==================
if __name__ == '__main__':
    print("✅ Setting up webhook...")
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL + WEBHOOK_PATH)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)