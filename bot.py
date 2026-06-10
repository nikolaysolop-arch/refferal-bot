import sqlite3
import random
import string
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

# Настройки
REFERRAL_REWARD = 15.0
REFERRED_REWARD = 10.0
DAILY_BONUS = 5.0
MIN_WITHDRAW = 100.0

# Промокоды
PROMO_CODES = {
    "START2025": 50.0,
    "BONUS100": 100.0,
    "FRIEND2025": 75.0
}

# Flask для Render
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# ==================== БАЗА ДАННЫХ ====================
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
                  last_daily TEXT,
                  joined_date TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    try:
        c.execute("INSERT INTO users (user_id, username, referrer_id, referral_code, joined_date) VALUES (?,?,?,?,?)",
                  (user_id, username, referrer_id, code, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return code
    except:
        conn.close()
        return None

def update_balance(user_id, amount):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    c.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_referral(referrer_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()

def get_referrals_count(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def can_claim_daily(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return True
    last = datetime.strptime(row[0], '%Y-%m-%d')
    return datetime.now().date() > last.date()

def claim_daily(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, DAILY_BONUS)

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard(user_id):
    row = get_user(user_id)
    balance = row[4] if row else 0
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💰 Баланс: {balance:.2f} ₽", callback_data="balance")],
        [InlineKeyboardButton("👥 Мои рефералы", callback_data="referrals")],
        [InlineKeyboardButton("🔗 Моя ссылка", callback_data="my_link")],
        [InlineKeyboardButton("🏆 Топ рефералов", callback_data="top")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily")],
        [InlineKeyboardButton("🎟 Промокод", callback_data="promo")],
        [InlineKeyboardButton("💸 Вывести деньги", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("💰 Заработать", callback_data="earn")],
        [InlineKeyboardButton("❓ Поддержка", callback_data="support")]
    ])
    return keyboard

# ==================== ОБРАБОТЧИКИ ====================
def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
    # Проверяем реферальный код
    ref_id = None
    if context.args:
        code = context.args[0]
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,))
        row = c.fetchone()
        conn.close()
        if row and row[0] != uid:
            ref_id = row[0]
    
    # Регистрация
    if not get_user(uid):
        create_user(uid, name, ref_id)
        if ref_id:
            update_balance(ref_id, REFERRAL_REWARD)
            add_referral(ref_id)
            update_balance(uid, REFERRED_REWARD)
            context.bot.send_message(ref_id, f"🎉 Новый реферал! @{name}\n💰 +{REFERRAL_REWARD} ₽")
            update.message.reply_text(f"🎉 Бонус {REFERRED_REWARD} ₽ за регистрацию!")
    
    update.message.reply_text(
        "🤝 <b>Реферальный бот</b>\n\n"
        "🔥 Зарабатывай с друзьями!\n\n"
        f"💰 За каждого друга: +{REFERRAL_REWARD} ₽\n"
        f"🎁 Другу бонус: +{REFERRED_REWARD} ₽\n"
        f"📅 Ежедневный бонус: +{DAILY_BONUS} ₽\n\n"
        "👇 Выбери действие:",
        parse_mode="HTML",
        reply_markup=main_keyboard(uid)
    )

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    user_row = get_user(uid)
    
    # === БАЛАНС ===
    if data == "balance":
        balance = user_row[4] if user_row else 0
        earned = user_row[5] if user_row else 0
        refs = user_row[6] if user_row else 0
        query.edit_message_text(
            f"💰 <b>Твой баланс</b>\n\n"
            f"Доступно: {balance:.2f} ₽\n"
            f"Всего заработано: {earned:.2f} ₽\n"
            f"Рефералов: {refs}\n\n"
            f"Минимум вывода: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # === МОЯ ССЫЛКА ===
    elif data == "my_link":
        code = user_row[3] if user_row else None
        if code:
            bot_info = context.bot.get_me()
            url = f"https://t.me/{bot_info.username}?start={code}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={url}&text=Зарабатывай со мной!")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back")]
            ])
            query.edit_message_text(
                f"🔗 <b>Твоя реферальная ссылка</b>\n\n<code>{url}</code>\n\nПриглашай друзей и получай бонусы!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
    
    # === МОИ РЕФЕРАЛЫ ===
    elif data == "referrals":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE referrer_id = ? LIMIT 20", (uid,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            query.edit_message_text("👥 У тебя пока нет рефералов.\nПригласи друзей!", reply_markup=main_keyboard(uid))
        else:
            text = f"👥 <b>Твои рефералы ({len(rows)})</b>\n\n"
            for i, r in enumerate(rows, 1):
                text += f"{i}. @{r[0] or 'скрыто'}\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))
    
    # === ТОП РЕФЕРАЛОВ ===
    elif data == "top":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            query.edit_message_text("🏆 Пока нет рефералов в топе.", reply_markup=main_keyboard(uid))
        else:
            text = "🏆 <b>Топ рефералов</b>\n\n"
            for i, (username, count) in enumerate(rows, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
                text += f"{medal} {i}. @{username or 'anon'} — {count} рефералов\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))
    
    # === ЕЖЕДНЕВНЫЙ БОНУС ===
    elif data == "daily":
        if can_claim_daily(uid):
            claim_daily(uid)
            query.edit_message_text(f"🎁 Ежедневный бонус получен!\n💰 +{DAILY_BONUS} ₽", reply_markup=main_keyboard(uid))
        else:
            query.edit_message_text("❌ Ты уже получал бонус сегодня. Заходи завтра!", reply_markup=main_keyboard(uid))
    
    # === ПРОМОКОД ===
    elif data == "promo":
        query.edit_message_text(
            "🎟 <b>Введи промокод</b>\n\n"
            "Доступные промокоды:\n"
            "• START2025 — 50 ₽\n"
            "• BONUS100 — 100 ₽\n"
            "• FRIEND2025 — 75 ₽\n\n"
            "Напиши код в чат одним сообщением:",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        context.user_data['awaiting_promo'] = True
    
    # === ВЫВОД ДЕНЕГ ===
    elif data == "withdraw":
        balance = user_row[4] if user_row else 0
        if balance < MIN_WITHDRAW:
            query.answer(f"❌ Минимум вывода {MIN_WITHDRAW} ₽. Твой баланс: {balance:.2f} ₽", show_alert=True)
            return
        context.bot.send_message(
            ADMIN_ID,
            f"💳 <b>ЗАЯВКА НА ВЫВОД</b>\n\n"
            f"👤 Пользователь: @{query.from_user.username}\n"
            f"🆔 ID: {uid}\n"
            f"💰 Сумма: {balance:.2f} ₽\n"
            f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML"
        )
        query.edit_message_text(
            f"✅ <b>Заявка отправлена!</b>\n\n"
            f"💰 Сумма: {balance:.2f} ₽\n"
            f"📝 Администратор свяжется с тобой в ближайшее время.",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # === СТАТИСТИКА ===
    elif data == "stats":
        balance = user_row[4] if user_row else 0
        earned = user_row[5] if user_row else 0
        refs = user_row[6] if user_row else 0
        joined = user_row[8] if user_row else "—"
        query.edit_message_text(
            f"📊 <b>Твоя статистика</b>\n\n"
            f"👥 Рефералов: {refs}\n"
            f"💰 Заработано: {earned:.2f} ₽\n"
            f"💳 Доступно: {balance:.2f} ₽\n"
            f"📅 В системе с: {joined[:10]}\n\n"
            f"⚡ Чтобы вывести деньги, накопи минимум {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # === ЗАРАБОТАТЬ (партнёрские ссылки) ===
    elif data == "earn":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 Ozon", url="https://ozon.ru/")],
            [InlineKeyboardButton("👕 Wildberries", url="https://wildberries.ru/")],
            [InlineKeyboardButton("📦 AliExpress", url="https://aliexpress.ru/")],
            [InlineKeyboardButton("💼 Kwork", url="https://kwork.ru/")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
        query.edit_message_text(
            "💰 <b>Дополнительный заработок</b>\n\n"
            "Переходи по ссылкам, совершай покупки и получай кэшбэк!\n\n"
            "<i>Ссылки ведут на популярные маркетплейсы.</i>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    # === ПОДДЕРЖКА ===
    elif data == "support":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Написать админу", url="https://t.me/mskvoru")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
        query.edit_message_text(
            "❓ <b>Поддержка</b>\n\n"
            "По всем вопросам:\n"
            "• Вывод средств\n"
            "• Проблемы с ботом\n"
            "• Сотрудничество\n\n"
            "Нажми на кнопку ниже:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    # === НАЗАД ===
    elif data == "back":
        query.edit_message_text("🤝 Главное меню:", reply_markup=main_keyboard(uid))

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    
    if context.user_data.get('awaiting_promo'):
        if text in PROMO_CODES:
            amount = PROMO_CODES[text]
            update_balance(user_id, amount)
            update.message.reply_text(
                f"✅ <b>Промокод активирован!</b>\n\n💰 Ты получил +{amount} ₽ бонуса.\n📊 Проверь баланс в меню.",
                parse_mode="HTML",
                reply_markup=main_keyboard(user_id)
            )
        else:
            update.message.reply_text(
                f"❌ <b>Неверный промокод</b>\n\nКод '{text}' не найден.\nПопробуй: START2025, BONUS100, FRIEND2025",
                parse_mode="HTML",
                reply_markup=main_keyboard(user_id)
            )
        context.user_data['awaiting_promo'] = False
    else:
        update.message.reply_text("🤝 Используй кнопки меню:", reply_markup=main_keyboard(user_id))

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(None, handle_message))
    
    updater.start_polling()
    print("Бот запущен!")
    updater.idle()
