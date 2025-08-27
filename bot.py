#!/usr/bin/env python3
"""
Full Telegram bot for Render Web Service:
- Flask keep-alive routes (/) and (/ping-test) — use /ping-test for UptimeRobot
- Telegram bot runs in a background thread
- Stores data in Postgres (Render DB recommended)
- Features: join-check, referral, balance, bonus, stock withdraw, admin broadcast
"""

import os
import time
import threading
import traceback

import telebot
from telebot import types
import psycopg2
from flask import Flask

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set. Set it via environment variable.")
ADMINS = [8048054789, 2115677414]  # keep as ints
CHANNELS = [
    {"id": "@jak_paradise", "url": "https://t.me/jak_paradise"},
    {"id": "-1002408750694", "url": "https://t.me/+tU7esamIk45jZTg0"},
    {"id": "-1002964116333", "url": "https://t.me/+yOTZqVq194s0OTk0"},
    {"id": "-1002793343378", "url": "https://t.me/+frT0WdQQPwQ1YzY0"}
]
CHANNEL_ID_FOR_REF = -1002964116333
SEND_DELAY = float(os.getenv("SEND_DELAY", "0.03"))  # seconds delay per send to be gentle on rate limits

# ---------------- Bot & Flask ----------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(_name_)

# ---------------- Postgres connection helper ----------------
PG_DB = os.getenv("PGDATABASE")
PG_USER = os.getenv("PGUSER")
PG_PASS = os.getenv("PGPASSWORD")
PG_HOST = os.getenv("PGHOST")
PG_PORT = os.getenv("PGPORT")

def get_conn():
    if not all([PG_DB, PG_USER, PG_PASS, PG_HOST, PG_PORT]):
        raise RuntimeError("Postgres environment variables not fully set.")
    return psycopg2.connect(dbname=PG_DB, user=PG_USER, password=PG_PASS, host=PG_HOST, port=PG_PORT)

# Initialize DB if needed
with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            referred_by BIGINT,
            last_bonus BIGINT DEFAULT 0
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id SERIAL PRIMARY KEY,
            reward TEXT
        );
        """)
    conn.commit()

# ---------------- Helpers ----------------
def is_admin(uid: int) -> bool:
    return uid in ADMINS

def send_to_admins(text: str, parse_mode=None):
    for a in ADMINS:
        try:
            bot.send_message(a, text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Failed notify admin {a}: {e}")

def format_user_info(user):
    name = getattr(user, "first_name", "") or ""
    uname = f"@{user.username}" if getattr(user, "username", None) else "❌ No Username"
    return f"•🥂 Name:- {name} • 🎀\nUsername :- {uname} 💎\nID: {user.id} ☠"

def add_user(user_id, username, ref_id=None, user=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (user_id, username, referred_by) VALUES (%s,%s,%s) ON CONFLICT (user_id) DO NOTHING", (user_id, username, ref_id))
        conn.commit()

    # notify admins and handle referral award
    if user:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total = cur.fetchone()[0]
        send_to_admins(f"🔔 New user started the bot:\nTotal :- {total}\n{format_user_info(user)}")

    if ref_id:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET balance = balance + 3 WHERE user_id = %s", (ref_id,))
            conn.commit()
        try:
            bot.send_message(ref_id, "🎉 You earned +3 💎 Diamonds (Referral Bonus)!")
        except Exception as e:
            print(f"Could not notify referrer {ref_id}: {e}")

def get_balance(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id=%s", (user_id,))
            r = cur.fetchone()
            return r[0] if r else 0

def update_balance(user_id, amount):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = balance + %s WHERE user_id=%s", (amount, user_id))
        conn.commit()

def _normalize_chat_id(chat_id_field):
    if isinstance(chat_id_field, int):
        return chat_id_field
    if isinstance(chat_id_field, str):
        if chat_id_field.startswith("@"):
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
            if getattr(member, "status", "") in ["left", "kicked"]:
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

# ---------------- Handlers ----------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    args = message.text.split()
    ref = None
    if len(args) > 1:
        try:
            ref = int(args[1])
        except:
            ref = None
    add_user(user_id, username, ref, message.from_user)
    if check_subscription(user_id):
        send_main_menu(user_id)
    else:
        send_join_prompt(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def callback_check(call):
    uid = call.from_user.id
    if check_subscription(uid):
        try:
            bot.edit_message_text("✅ Thank you for joining! Now you can use the bot freely.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except:
            pass
        send_main_menu(uid)
    else:
        bot.answer_callback_query(call.id, "❌ Please join all required channels first!")

# ========== Admin: Stock ==========
@bot.message_handler(commands=['addstock'])
def add_stock(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠ Usage: /addstock Reward Text")
        return
    reward = args[1]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO stock (reward) VALUES (%s)", (reward,))
        conn.commit()
    bot.reply_to(message, f"✅ Stock added:\n{reward}")

@bot.message_handler(commands=['checkstock'])
def check_stock(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command!")
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stock")
            c = cur.fetchone()[0]
    bot.reply_to(message, f"📦 Current stock count: {c} item(s)")

@bot.message_handler(commands=['stocklist'])
def stock_list(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command!")
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, reward FROM stock ORDER BY id")
            rows = cur.fetchall()
    if not rows:
        bot.reply_to(message, "📦 Stock is empty.")
        return
    text = "📦 Current Stock Items:\n\n"
    for sid, reward in rows:
        text += f"ID: {sid} | Reward: {reward}\n"
    bot.reply_to(message, text)

# ========== Admin: Broadcast ==========
@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        send_broadcast_text(message.from_user.id, args[1])
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Forward Mode", callback_data="broadcast_forward"))
        markup.add(types.InlineKeyboardButton("📝 Resend Mode", callback_data="broadcast_resend"))
        bot.send_message(message.chat.id, "📢 Choose broadcast mode:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["broadcast_forward", "broadcast_resend"])
def choose_broadcast_mode(call):
    if not is_admin(call.from_user.id):
        return
    mode = "forward" if call.data == "broadcast_forward" else "resend"
    m = bot.send_message(call.message.chat.id, "📩 Please send the content (text/photo/video/document/audio/voice/sticker/GIF) you want to broadcast.")
    bot.register_next_step_handler(m, lambda mm: process_broadcast(mm, mode))

def process_broadcast(message, mode):
    if not is_admin(message.from_user.id):
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            users = [r[0] for r in cur.fetchall()]
    total = len(users)
    sent = 0
    failed = 0
    errors = []
    for uid in users:
        try:
            if mode == "forward":
                bot.forward_message(uid, message.chat.id, message.message_id)
            else:
                ct = message.content_type
                if ct == "text":
                    bot.send_message(uid, f"📢 <b>Admin Message:</b>\n\n{message.text}", parse_mode="HTML")
                elif ct == "photo":
                    bot.send_photo(uid, message.photo[-1].file_id, caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "video":
                    bot.send_video(uid, message.video.file_id, caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "document":
                    bot.send_document(uid, message.document.file_id, caption=f"📢 <b>Admin Message:</b>\n\n{message.caption or ''}", parse_mode="HTML")
                elif ct == "voice":
                    bot.send_voice(uid, message.voice.file_id)
                elif ct == "audio":
                    bot.send_audio(uid, message.audio.file_id)
                elif ct == "sticker":
                    bot.send_sticker(uid, message.sticker.file_id)
                elif ct == "animation":
                    bot.send_animation(uid, message.animation.file_id, caption=f"{message.caption or ''}")
                else:
                    bot.send_message(uid, "📢 Admin sent an update (unsupported media type).")
            sent += 1
        except Exception as e:
            failed += 1
            errors.append(f"User {uid}: {e}")
        finally:
            time.sleep(SEND_DELAY)
    # report
    report = (
        "📢 <b>Broadcast Status</b>\n\n"
        f"👥 Total Users in Bot: <b>{total}</b>\n"
        f"📩 Messages Sent: <b>{sent}</b>\n"
        f"❌ Failed to Send: <b>{failed}</b>\n"
    )
    if errors:
        report += "\n\n⚠ Errors (sample):\n" + "\n".join(errors[:8])
    bot.send_message(message.from_user.id, report, parse_mode="HTML")

def send_broadcast_text(admin_id, text):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            users = [r[0] for r in cur.fetchall()]
    total = len(users)
    sent = 0
    failed = 0
    errors = []
    for uid in users:
        try:
            bot.send_message(uid, f"📢 <b>Admin Message:</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            errors.append(f"User {uid}: {e}")
        finally:
            time.sleep(SEND_DELAY)
    report = (
        "📢 <b>Broadcast Status</b>\n\n"
        f"👥 Total Users in Bot: <b>{total}</b>\n"
        f"📩 Messages Sent: <b>{sent}</b>\n"
        f"❌ Failed to Send: <b>{failed}</b>\n"
    )
    if errors:
        report += "\n\n⚠ Errors (sample):\n" + "\n".join(errors[:8])
    bot.send_message(admin_id, report, parse_mode="HTML")

# ========== User menu and withdraw ==========
@bot.message_handler(func=lambda m: True)
def menu_handler(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    # nudge join if not joined
    if not check_subscription(uid):
        send_join_prompt(uid)
        return
    if txt == "💎 Balance":
        bal = get_balance(uid)
        bot.send_message(uid, f"💎 Your Balance: {bal} Diamonds")
    elif txt == "👥 Referral Link":
        bot_info = bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={uid}"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (uid,))
                refs = cur.fetchone()[0]
        bot.send_message(uid, f"🔗 Your referral link:\n{link}\n\n👥 Referrals: {refs}\n💎 Per Referral: 3 Diamonds")
    elif txt == "🎁 Bonus":
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT last_bonus FROM users WHERE user_id=%s", (uid,))
                row = cur.fetchone()
                last = row[0] if row and row[0] else 0
        now = int(time.time())
        if now - last >= 86400:
            update_balance(uid, 2)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET last_bonus=%s WHERE user_id=%s", (now, uid))
                conn.commit()
            bot.send_message(uid, "🎁 You received +2 💎 Diamonds (Daily Bonus)!")
        else:
            rem = 86400 - (now - last)
            hrs = rem // 3600
            mins = (rem % 3600) // 60
            bot.send_message(uid, f"⏳ Bonus already claimed! Try again in {hrs}h {mins}m.")
    elif txt == "⚡ Withdraw":
        bal = get_balance(uid)
        if bal >= 7:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Confirm", callback_data="withdraw_confirm"))
            bot.send_message(uid, f"💎 Your Balance: {bal} Diamonds\n\n⚠ 7 Diamonds are required to withdraw.\n\n👉 Do you want to exchange 7 Diamonds for a reward?", reply_markup=markup)
        else:
            bot.send_message(uid, f"❌ You need at least 7 💎 Diamonds to withdraw. You have {bal}.")
    elif txt == "🆘 Support":
        bot.send_message(uid, "📩 For help, contact admin: @Jakhelper_bot")
    else:
        bot.send_message(uid, "❓ Unknown command. Use the menu buttons.")

@bot.callback_query_handler(func=lambda call: call.data == "withdraw_confirm")
def confirm_withdraw(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    if bal >= 7:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, reward FROM stock ORDER BY id LIMIT 1")
                row = cur.fetchone()
        if row:
            sid, reward = row
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM stock WHERE id=%s", (sid,))
                conn.commit()
            update_balance(uid, -7)
            try:
                bot.send_message(uid, reward)
            except Exception as e:
                print(f"Failed to send reward to {uid}: {e}")
            withdraw_msg = f"💎 Request for withdrawal of 7 Diamonds created successfully!\n\nUser: @{call.from_user.username}\n\nBot :- @{bot.get_me().username}"
            try:
                bot.send_message(CHANNEL_ID_FOR_REF, withdraw_msg)
            except Exception as e:
                print(f"Failed to notify channel: {e}")
            send_to_admins(withdraw_msg)
        else:
            bot.send_message(uid, "❌ Sorry, stock is empty. Message admin: @Jakhelper_bot")
    else:
        bot.send_message(uid, "❌ You don’t have enough Diamonds.")

# ---------------- Flask keep-alive endpoints ----------------
@app.route("/")
def home():
    return "🤖 Telegram bot is running!", 200

@app.route("/ping-test")
def ping_test():
    return "Bot is alive 🚀", 200

# ---------------- Bot runner ----------------
def run_bot_loop():
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=15)
        except Exception as e:
            print("Bot crashed, restarting in 5s...", e)
            traceback.print_exc()
            time.sleep(5)

if _name_ == "_main_":
    t = threading.Thread(target=run_bot_loop)
    t.daemon = True
    t.start()
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)