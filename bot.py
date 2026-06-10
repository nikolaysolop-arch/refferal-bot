import sqlite3
import random
import string
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

# Настройки
REFERRAL_REWARD = 15.0
REFERRED_REWARD = 10.0
DAILY_BONUS = 5.0
MIN_WITHDRAW = 100.0

# Партнёрские ссылки (ЗАМЕНИ НА СВОИ)
PARTNER_LINKS = {
    "ozon": "https://ozon.ru/?partner=YOUR_ID",           # Регистрация: ozon.ru/partners
    "wildberries": "https://wildberries.ru/?partner=YOUR_ID",  # partners.wildberries.ru
    "aliexpress": "https://aliexpress.ru/?partner=YOUR_ID",    # portaal.aliexpress.com
    "kwork": "https://kwork.ru/?ref=YOUR_ID",                  # kwork.ru/refprogram
    "yandex": "https://market.yandex.ru/partner=YOUR_ID",      # yandex.ru/adv/partners
}

# Промокоды для бонусов
PROMO_CODES = {
    "START2025": 50.0,
    "BONUS100": 100.0,
    "FRIEND2025": 75.0
}

# Коды для рекламы Telega.in (получить в кабинете)
TELEGA_IN_ID = "YOUR_ID"

# Flask для Render
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK"

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
                  clicks INTEGER DEFAULT 0,
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

def add_click(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET clicks = clicks + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_earned) FROM users")
    total_earned = c.fetchone()[0] or 0
    conn.close()
    return total_users, total_earned

def can_claim_daily(user_id):
    row = get_user(user_id)
    if not row or not row[7]:
        return True
    last = datetime.strptime(row[7], '%Y-%m-%d')
    return datetime.now().date() > last.date()

def claim_daily(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, DAILY_BONUS)

def apply_promo(user_id, code):
    if code in PROMO_CODES:
        amount = PROMO_CODES[code]
        update_balance(user_id, amount)
        return True, amount
    return False, 0

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard(user_id):
    row = get_user(user_id)
    balance = row[4] if row else 0
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💰 Баланс: {balance:.2f} ₽", callback_data="balance")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referrals"), InlineKeyboardButton("🔗 Моя ссылка", callback_data="my_link")],
        [InlineKeyboardButton("🏆 Топ рефералов", callback_data="top")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily"), InlineKeyboardButton("🎟 Промокод", callback_data="promo")],
        [InlineKeyboardButton("💰 ЗАРАБОТАТЬ", callback_data="earn")],
        [InlineKeyboardButton("💸 Вывести деньги", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("❓ Поддержка", callback_data="support")]
    ])
    return keyboard

def get_earn_keyboard():
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Ozon (кэшбэк 15%)", url=PARTNER_LINKS['ozon']),
         InlineKeyboardButton("👕 Wildberries (12%)", url=PARTNER_LINKS['wildberries'])],
        [InlineKeyboardButton("📦 AliExpress (10%)", url=PARTNER_LINKS['aliexpress']),
         InlineKeyboardButton("💼 Kwork (20%)", url=PARTNER_LINKS['kwork'])],
        [InlineKeyboardButton("📱 Яндекс.Маркет (8%)", url=PARTNER_LINKS['yandex'])],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])
    return keyboard

# ==================== ОБРАБОТЧИКИ ====================
def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
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
    
    if not get_user(uid):
        create_user(uid, name, ref_id)
        if ref_id:
            update_balance(ref_id, REFERRAL_REWARD)
            add_referral(ref_id)
            update_balance(uid, REFERRED_REWARD)
            context.bot.send_message(ref_id, f"🎉 Новый реферал! @{name}\n💰 +{REFERRAL_REWARD} ₽")
            update.message.reply_text(f"🎉 Бонус {REFERRED_REWARD} ₽ за регистрацию!")
    
    update.message.reply_text(
        "🤝 <b>РЕФЕРАЛЬНЫЙ БОТ | ЗАРАБОТОК</b>\n\n"
        "🔥 <b>Как заработать:</b>\n"
        "• Приглашай друзей → +15 ₽ за каждого\n"
        "• Забирай ежедневный бонус → +5 ₽\n"
        "• Используй промокоды → до +100 ₽\n"
        "• Переходи по партнёрским ссылкам → кэшбэк до 20%\n\n"
        f"💎 Твой код: <code>{get_user(uid)[3]}</code>\n\n"
        "👇 Выбери действие:",
        parse_mode="HTML",
        reply_markup=main_keyboard(uid)
    )

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    row = get_user(uid)
    
    # БАЛАНС
    if data == "balance":
        balance = row[4] if row else 0
        earned = row[5] if row else 0
        refs = row[6] if row else 0
        query.edit_message_text(
            f"💰 <b>Твой баланс</b>\n\n"
            f"💵 Доступно: {balance:.2f} ₽\n"
            f"📈 Заработано всего: {earned:.2f} ₽\n"
            f"👥 Приглашено: {refs}\n\n"
            f"⚡ Минимум вывода: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # МОЯ ССЫЛКА
    elif data == "my_link":
        code = row[3] if row else None
        if code:
            bot_info = context.bot.get_me()
            url = f"https://t.me/{bot_info.username}?start={code}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={url}&text=Зарабатывай со мной!")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back")]
            ])
            query.edit_message_text(
                f"🔗 <b>Твоя реферальная ссылка</b>\n\n<code>{url}</code>\n\n📢 Приглашай друзей и получай +{REFERRAL_REWARD} ₽ за каждого!",
                parse_mode="HTML",
                reply_markup=keyboard
            )
    
    # РЕФЕРАЛЫ
    elif data == "referrals":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE referrer_id = ? LIMIT 20", (uid,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            query.edit_message_text("👥 У тебя пока нет рефералов.\nПригласи друзей по своей ссылке!", reply_markup=main_keyboard(uid))
        else:
            text = f"👥 <b>Твои рефералы ({len(rows)})</b>\n\n"
            for i, r in enumerate(rows, 1):
                text += f"{i}. @{r[0] or 'скрыто'}\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))
    
    # ТОП
    elif data == "top":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            query.edit_message_text("🏆 Пока нет рефералов в топе. Будь первым!", reply_markup=main_keyboard(uid))
        else:
            text = "🏆 <b>Топ рефералов</b>\n\n"
            for i, (username, count) in enumerate(rows, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
                text += f"{medal} {i}. @{username or 'anon'} — {count} рефералов\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))
    
    # ЕЖЕДНЕВНЫЙ БОНУС
    elif data == "daily":
        if can_claim_daily(uid):
            claim_daily(uid)
            query.edit_message_text(f"🎁 Ежедневный бонус получен!\n💰 +{DAILY_BONUS} ₽", reply_markup=main_keyboard(uid))
        else:
            query.edit_message_text("❌ Ты уже получал бонус сегодня.\n📅 Заходи завтра!", reply_markup=main_keyboard(uid))
    
    # ПРОМОКОД
    elif data == "promo":
        query.edit_message_text(
            "🎟 <b>Введи промокод</b>\n\n"
            "Доступные промокоды:\n"
            "• START2025 → 50 ₽\n"
            "• BONUS100 → 100 ₽\n"
            "• FRIEND2025 → 75 ₽\n\n"
            "Напиши код в чат:",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        context.user_data['awaiting_promo'] = True
    
    # ВЫВОД
    elif data == "withdraw":
        balance = row[4] if row else 0
        if balance < MIN_WITHDRAW:
            query.answer(f"❌ Минимум {MIN_WITHDRAW} ₽. Твой баланс: {balance:.2f} ₽", show_alert=True)
            return
        context.bot.send_message(
            ADMIN_ID,
            f"💳 <b>ЗАЯВКА НА ВЫВОД</b>\n\n"
            f"👤 @{query.from_user.username}\n"
            f"🆔 ID: {uid}\n"
            f"💰 Сумма: {balance:.2f} ₽\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML"
        )
        query.edit_message_text(
            f"✅ <b>Заявка отправлена!</b>\n\n"
            f"💰 Сумма: {balance:.2f} ₽\n"
            f"📝 Администратор свяжется в ближайшее время.",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # СТАТИСТИКА
    elif data == "stats":
        balance = row[4] if row else 0
        earned = row[5] if row else 0
        refs = row[6] if row else 0
        clicks = row[7] if row else 0
        joined = row[8] if row else "—"
        total_users, total_earned_all = get_stats()
        query.edit_message_text(
            f"📊 <b>Твоя статистика</b>\n\n"
            f"👥 Рефералов: {refs}\n"
            f"💰 Заработано: {earned:.2f} ₽\n"
            f"💳 Доступно: {balance:.2f} ₽\n"
            f"🖱 Переходов: {clicks}\n"
            f"📅 В системе с: {joined[:10]}\n\n"
            f"📈 <b>Общая статистика бота</b>\n"
            f"👤 Всего пользователей: {total_users}\n"
            f"💰 Всего заработано: {total_earned_all:.2f} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    
    # ЗАРАБОТАТЬ (партнёрские ссылки)
    elif data == "earn":
        add_click(uid)
        query.edit_message_text(
            "💰 <b>Дополнительный заработок</b>\n\n"
            "🔥 Переходи по ссылкам и зарабатывай:\n"
            "• Кэшбэк до 20% на покупках\n"
            "• Бонусы за регистрацию\n"
            "• Партнёрские программы\n\n"
            "<i>Каждый переход увеличивает твой рейтинг!</i>",
            parse_mode="HTML",
            reply_markup=get_earn_keyboard()
        )
    
    # ПОДДЕРЖКА
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
    
    # НАЗАД
    elif data == "back":
        query.edit_message_text("🤝 Главное меню:", reply_markup=main_keyboard(uid))

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    
    if context.user_data.get('awaiting_promo'):
        success, amount = apply_promo(user_id, text)
        if success:
            update.message.reply_text(f"✅ <b>Промокод активирован!</b>\n\n💰 +{amount} ₽", parse_mode="HTML", reply_markup=main_keyboard(user_id))
        else:
            update.message.reply_text(f"❌ <b>Неверный промокод</b>\n\nПопробуй: START2025, BONUS100, FRIEND2025", parse_mode="HTML", reply_markup=main_keyboard(user_id))
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
    dp.add_handler(MessageHandler(Filters.text, handle_message))
    
    updater.start_polling()
    print("🤖 Бот запущен!")
    updater.idle()
