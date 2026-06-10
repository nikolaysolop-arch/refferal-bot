import sqlite3
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

REFERRAL_REWARD = 10.0
REFERRED_REWARD = 5.0
MIN_WITHDRAW = 50.0

def init_db():
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  referrer_id INTEGER,
                  referral_code TEXT UNIQUE,
                  balance REAL DEFAULT 0,
                  total_earned REAL DEFAULT 0,
                  referrals_count INTEGER DEFAULT 0,
                  joined_date TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'user_id': row[0], 'username': row[1], 'referrer_id': row[2],
                'referral_code': row[3], 'balance': row[4], 'total_earned': row[5],
                'referrals_count': row[6], 'joined_date': row[7]}
    return None

def create_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    try:
        c.execute("INSERT INTO users (user_id, username, referrer_id, referral_code, joined_date) VALUES (?,?,?,?,?)",
                  (user_id, username, referrer_id, code, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def update_balance(user_id, amount):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    if amount > 0:
        c.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_referral(referrer_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()

def main_keyboard(user_id):
    u = get_user(user_id)
    bal = u['balance'] if u else 0
    keyboard = [
        [InlineKeyboardButton(f"💰 Баланс: {bal:.2f} ₽", callback_data='bal')],
        [InlineKeyboardButton("👥 Мои рефералы", callback_data='refs')],
        [InlineKeyboardButton("🔗 Моя ссылка", callback_data='link')],
        [InlineKeyboardButton("💸 Вывести", callback_data='out')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stat')]
    ]
    return InlineKeyboardMarkup(keyboard)

def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    ref_id = None
    if context.args:
        code = context.args[0]
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,))
        r = c.fetchone()
        conn.close()
        if r and r[0] != uid:
            ref_id = r[0]
    if not get_user(uid):
        create_user(uid, name, ref_id)
        if ref_id:
            update_balance(ref_id, REFERRAL_REWARD)
            add_referral(ref_id)
            update_balance(uid, REFERRED_REWARD)
            context.bot.send_message(ref_id, f"🎉 +{REFERRAL_REWARD} ₽ за реферала @{name}")
            update.message.reply_text(f"🎉 Бонус {REFERRED_REWARD} ₽ за регистрацию!")
    update.message.reply_text("🤝 Реферальный бот\n👇 Меню:", reply_markup=main_keyboard(uid))

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    u = get_user(uid)
    
    if data == 'bal':
        query.edit_message_text(f"💰 Баланс: {u['balance']:.2f} ₽\nВсего: {u['total_earned']:.2f} ₽\nРефералов: {u['referrals_count']}", reply_markup=main_keyboard(uid))
    elif data == 'link':
        url = f"https://t.me/{context.bot.username}?start={u['referral_code']}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={url}")], [InlineKeyboardButton("🔙 Назад", callback_data='menu')]])
        query.edit_message_text(f"🔗 Твоя ссылка:\n<code>{url}</code>", parse_mode='HTML', reply_markup=keyboard)
    elif data == 'refs':
        if u['referrals_count'] == 0:
            query.edit_message_text("👥 Нет рефералов", reply_markup=main_keyboard(uid))
            return
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE referrer_id = ? LIMIT 10", (uid,))
        rows = c.fetchall()
        conn.close()
        txt = f"👥 Рефералы ({u['referrals_count']}):\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. @{r[0] or 'anon'}\n"
        query.edit_message_text(txt, reply_markup=main_keyboard(uid))
    elif data == 'stat':
        query.edit_message_text(f"📊 Рефералов: {u['referrals_count']}\n💰 Заработано: {u['total_earned']:.2f} ₽\n💳 Доступно: {u['balance']:.2f} ₽", reply_markup=main_keyboard(uid))
    elif data == 'out':
        if u['balance'] < MIN_WITHDRAW:
            query.answer(f"❌ Минимум {MIN_WITHDRAW} ₽", show_alert=True)
            return
        context.bot.send_message(ADMIN_ID, f"💳 ЗАЯВКА\n@{query.from_user.username}\nСумма: {u['balance']:.2f} ₽")
        query.edit_message_text("✅ Заявка отправлена", reply_markup=main_keyboard(uid))
    elif data == 'menu':
        query.edit_message_text("🤝 Главное меню:", reply_markup=main_keyboard(uid))

if __name__ == "__main__":
    init_db()
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    updater.start_polling()
    updater.idle()
