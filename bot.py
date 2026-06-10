import sqlite3
import random
import string
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

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
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"💰 Баланс: {bal:.2f} ₽", callback_data="bal"))
    kb.add(InlineKeyboardButton("👥 Мои рефералы", callback_data="refs"))
    kb.add(InlineKeyboardButton("🔗 Моя ссылка", callback_data="link"))
    kb.add(InlineKeyboardButton("💸 Вывести", callback_data="out"))
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="stat"))
    return kb

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    uid = msg.from_user.id
    name = msg.from_user.username or msg.from_user.first_name
    ref_id = None
    if ' ' in msg.text:
        code = msg.text.split()[1]
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
            await bot.send_message(ref_id, f"🎉 +{REFERRAL_REWARD} ₽ за реферала @{name}")
            await msg.answer(f"🎉 Бонус {REFERRED_REWARD} ₽ за регистрацию!")
    await msg.answer("🤝 Реферальный бот\n👇 Меню:", reply_markup=main_keyboard(uid))

@dp.callback_query_handler(lambda c: c.data == "bal")
async def bal(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    if u:
        await call.message.edit_text(f"💰 Баланс: {u['balance']:.2f} ₽\nВсего: {u['total_earned']:.2f} ₽\nРефералов: {u['referrals_count']}", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "link")
async def link(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    me = await bot.get_me()
    url = f"https://t.me/{me.username}?start={u['referral_code']}"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={url}"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu"))
    await call.message.edit_text(f"🔗 Твоя ссылка:\n<code>{url}</code>", parse_mode="HTML", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "refs")
async def refs(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    if u['referrals_count'] == 0:
        await call.message.edit_text("👥 Нет рефералов", reply_markup=main_keyboard(call.from_user.id))
        await call.answer()
        return
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE referrer_id = ? LIMIT 10", (call.from_user.id,))
    rows = c.fetchall()
    conn.close()
    txt = f"👥 Рефералы ({u['referrals_count']}):\n"
    for i, r in enumerate(rows, 1):
        txt += f"{i}. @{r[0] or 'anon'}\n"
    await call.message.edit_text(txt, reply_markup=main_keyboard(call.from_user.id))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "stat")
async def stat(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    await call.message.edit_text(f"📊 Рефералов: {u['referrals_count']}\n💰 Заработано: {u['total_earned']:.2f} ₽\n💳 Доступно: {u['balance']:.2f} ₽", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "out")
async def out(call: types.CallbackQuery):
    u = get_user(call.from_user.id)
    if u['balance'] < MIN_WITHDRAW:
        await call.answer(f"❌ Минимум {MIN_WITHDRAW} ₽", show_alert=True)
        return
    await bot.send_message(ADMIN_ID, f"💳 ЗАЯВКА\n@{call.from_user.username}\nСумма: {u['balance']:.2f} ₽")
    await call.message.edit_text("✅ Заявка отправлена", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("🤝 Главное меню:", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()

if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
