import sqlite3
import random
import string
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

REFERRAL_REWARD = 10.0
REFERRED_REWARD = 5.0
MIN_WITHDRAW = 50.0
DAILY_BONUS = 3.0

# Flask приложение для Render
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Referral bot is running!"

@flask_app.route('/health')
def health():
    return "OK"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

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
                  last_daily DATE,
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
                'referrals_count': row[6], 'last_daily': row[7], 'joined_date': row[8]}
    return None

def create_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    try:
        c.execute("INSERT INTO users (user_id, username, referrer_id, referral_code, last_daily, joined_date) VALUES (?,?,?,?,?,?)",
                  (user_id, username, referrer_id, code, None, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
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

def can_claim_daily(user_id):
    user = get_user(user_id)
    if not user or not user['last_daily']:
        return True
    last = datetime.strptime(user['last_daily'], '%Y-%m-%d')
    return datetime.now().date() > last.date()

def claim_daily(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, DAILY_BONUS)

def get_top_referrals(limit=10):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def apply_promo(user_id, code):
    # Промокоды: NEW2025, BONUS50, WELCOME
    promos = {
        "NEW2025": 50.0,
        "BONUS50": 50.0,
        "WELCOME": 30.0
    }
    if code in promos:
        amount = promos[code]
        update_balance(user_id, amount)
        return True, amount
    return False, 0

def main_keyboard(user_id):
    u = get_user(user_id)
    bal = u['balance'] if u else 0
    keyboard = [
        [InlineKeyboardButton(f"💰 Баланс: {bal:.2f} ₽", callback_data='bal')],
        [InlineKeyboardButton("👥 Мои рефералы", callback_data='refs')],
        [InlineKeyboardButton("🔗 Моя ссылка", callback_data='link')],
        [InlineKeyboardButton("🏆 Топ рефералов", callback_data='top')],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data='daily')],
        [InlineKeyboardButton("🎟 Промокод", callback_data='promo')],
        [InlineKeyboardButton("💸 Вывести", callback_data='out')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stat')],
        [InlineKeyboardButton("❓ Поддержка", callback_data='support')]
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
            # Уведомление админу
            context.bot.send_message(ADMIN_ID, f"👥 Новый реферал!\n@{name} перешёл по ссылке @{get_user(ref_id)['username']}")
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
    elif data == 'top':
        top = get_top_referrals()
        if not top:
            query.edit_message_text("🏆 Топ рефералов пока пуст", reply_markup=main_keyboard(uid))
            return
        txt = "🏆 <b>Топ рефералов</b>\n\n"
        for i, (username, count) in enumerate(top, 1):
            txt += f"{i}. @{username or 'anon'} — {count} рефералов\n"
        query.edit_message_text(txt, parse_mode='HTML', reply_markup=main_keyboard(uid))
    elif data == 'daily':
        if can_claim_daily(uid):
            claim_daily(uid)
            query.edit_message_text(f"🎁 Ты получил {DAILY_BONUS} ₽ бонуса!\nЗаходи завтра снова.", reply_markup=main_keyboard(uid))
        else:
            query.edit_message_text("❌ Ты уже забирал бонус сегодня. Заходи завтра!", reply_markup=main_keyboard(uid))
    elif data == 'promo':
        query.edit_message_text("🎟 Введи промокод:\nНапример: <code>NEW2025</code>", parse_mode='HTML', reply_markup=main_keyboard(uid))
        context.user_data['awaiting_promo'] = True
    elif data == 'stat':
        query.edit_message_text(f"📊 Рефералов: {u['referrals_count']}\n💰 Заработано: {u['total_earned']:.2f} ₽\n💳 Доступно: {u['balance']:.2f} ₽", reply_markup=main_keyboard(uid))
    elif data == 'out':
        if u['balance'] < MIN_WITHDRAW:
            query.answer(f"❌ Минимум {MIN_WITHDRAW} ₽", show_alert=True)
            return
        context.bot.send_message(ADMIN_ID, f"💳 ЗАЯВКА НА ВЫВОД\n👤 @{query.from_user.username}\n💰 Сумма: {u['balance']:.2f} ₽\n🆔 ID: {uid}")
        query.edit_message_text("✅ Заявка отправлена! Админ свяжется.", reply_markup=main_keyboard(uid))
    elif data == 'support':
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📩 Написать админу", url=f"https://t.me/{context.bot.username}?start=admin")]])
        query.edit_message_text("❓ По всем вопросам пиши админу:\nКнопка ниже", reply_markup=keyboard)
    elif data == 'menu':
        query.edit_message_text("🤝 Главное меню:", reply_markup=main_keyboard(uid))

def handle_message(update: Update, context):
    if context.user_data.get('awaiting_promo'):
        code = update.message.text.strip().upper()
        success, amount = apply_promo(update.effective_user.id, code)
        if success:
            update.message.reply_text(f"✅ Промокод активирован! Ты получил {amount} ₽ бонуса.", reply_markup=main_keyboard(update.effective_user.id))
        else:
            update.message.reply_text("❌ Неверный промокод. Попробуй ещё раз или обратись к админу.", reply_markup=main_keyboard(update.effective_user.id))
        context.user_data['awaiting_promo'] = False

if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(None, handle_message))
    updater.start_polling()
    updater.idle()
