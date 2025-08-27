import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import threading
from flask import Flask, request
import os
from contextlib import contextmanager

# Initialize Flask app (for web server functionality)
app = Flask(__name__)

# Initialize bot with your token
bot = telebot.TeleBot("YOUR_BOT_TOKEN_HERE")

# Database setup with connection pooling
def init_db():
    with sqlite3.connect('bot_database.db', check_same_thread=False, timeout=30) as conn:
        cursor = conn.cursor()
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create stock table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reward TEXT,
                claimed INTEGER DEFAULT 0,
                claim_date TIMESTAMP
            )
        ''')
        conn.commit()

# Database connection context manager
@contextmanager
def get_db_connection():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_db_cursor():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

# Initialize database
init_db()

# Helper functions with retry logic for database operations
def update_balance(user_id, amount, retries=5):
    for attempt in range(retries):
        try:
            with get_db_cursor() as cursor:
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
                if cursor.rowcount == 0:
                    # User doesn't exist, create them
                    cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, amount))
                return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise e
    return False

def get_balance(user_id):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        return result['balance'] if result else 0

def add_stock(reward_text, retries=5):
    for attempt in range(retries):
        try:
            with get_db_cursor() as cursor:
                cursor.execute("INSERT INTO stock (reward) VALUES (?)", (reward_text,))
                return cursor.lastrowid
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise e
    return None

def get_available_stock():
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, reward FROM stock WHERE claimed = 0 ORDER BY id LIMIT 1")
        return cursor.fetchone()

def claim_stock(stock_id, user_id, retries=5):
    for attempt in range(retries):
        try:
            with get_db_cursor() as cursor:
                # Mark stock as claimed
                cursor.execute("UPDATE stock SET claimed = 1, claim_date = CURRENT_TIMESTAMP WHERE id = ? AND claimed = 0", (stock_id,))
                if cursor.rowcount > 0:
                    # Update user balance
                    update_balance(user_id, 7)
                    return True
                return False
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < retries - 1:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise e
    return False

# Bot command handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Ensure user exists in database
    update_balance(user_id, 0)
    
    welcome_text = (
        "👋 Welcome to the Instagram Rewards Bot!\n\n"
        "Earn rewards by completing tasks and withdraw your earnings.\n\n"
        "Available commands:\n"
        "/balance - Check your current balance\n"
        "/addstock - Add new stock (admin only)\n"
        "/withdraw - Withdraw your earnings"
    )
    
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['balance'])
def show_balance(message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    
    bot.reply_to(message, f"💰 Your current balance: ${balance}")

@bot.message_handler(commands=['addstock'])
def add_stock_command(message):
    user_id = message.from_user.id
    # Check if user is admin (you should replace with your admin ID)
    if user_id != YOUR_ADMIN_USER_ID:
        bot.reply_to(message, "❌ This command is for administrators only.")
        return
    
    # Ask for stock reward text
    msg = bot.reply_to(message, "Please enter the reward text for the new stock:")
    bot.register_next_step_handler(msg, process_stock_reward)

def process_stock_reward(message):
    reward_text = message.text
    stock_id = add_stock(reward_text)
    
    if stock_id:
        bot.reply_to(message, f"✅ Stock added successfully! ID: {stock_id}")
    else:
        bot.reply_to(message, "❌ Failed to add stock. Please try again.")

@bot.message_handler(commands=['withdraw'])
def withdraw_command(message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    
    if balance < 7:
        bot.reply_to(message, "❌ You need at least $7 to withdraw.")
        return
    
    # Get available stock
    stock = get_available_stock()
    
    if not stock:
        bot.reply_to(message, "❌ No stock available at the moment. Please try again later.")
        return
    
    # Create confirmation keyboard
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("✅ Confirm", callback_data=f"withdraw_confirm_{stock['id']}"),
        InlineKeyboardButton("❌ Cancel", callback_data="withdraw_cancel")
    )
    
    bot.send_message(
        message.chat.id,
        f"📦 Available reward: {stock['reward']}\n\n"
        f"💰 Withdrawal amount: $7\n"
        f"📝 Please confirm your withdrawal:",
        reply_markup=keyboard
    )

# Callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    
    if call.data.startswith("withdraw_confirm_"):
        stock_id = int(call.data.split("_")[2])
        
        if claim_stock(stock_id, user_id):
            bot.answer_callback_query(call.id, "✅ Withdrawal successful! $7 has been added to your balance.")
            bot.edit_message_text(
                "✅ Withdrawal completed successfully!\n\n"
                f"📦 Reward: {get_stock_reward(stock_id)}\n"
                f"💰 Amount: $7",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ Withdrawal failed. This stock may have been claimed already.")
    
    elif call.data == "withdraw_cancel":
        bot.answer_callback_query(call.id, "Withdrawal cancelled.")
        bot.edit_message_text(
            "❌ Withdrawal cancelled.",
            call.message.chat.id,
            call.message.message_id
        )

def get_stock_reward(stock_id):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT reward FROM stock WHERE id = ?", (stock_id,))
        result = cursor.fetchone()
        return result['reward'] if result else "Unknown"

# Flask routes for health checks (required by Render)
@app.route('/')
def home():
    return "Telegram bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 403

# Run the bot
def run_bot():
    print("🚀 Starting Telegram bot...")
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"Bot polling failed: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Start bot in a separate thread
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Start Flask app (for web server)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)