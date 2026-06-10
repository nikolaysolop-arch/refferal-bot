import sqlite3
import random
import string
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

# ==================== КОНФИГ ====================
BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408
ADMIN_PASSWORD = "1997"  # Пароль для входа в админ-панель

# Настройки
REFERRAL_REWARD = 15.0
REFERRED_REWARD = 10.0
DAILY_BONUS = 5.0
MIN_WITHDRAW = 100.0

# Партнёрские ссылки
PARTNER_LINKS = {
    "ozon": "https://ozon.ru/?partner=YOUR_ID",
    "wildberries": "https://wildberries.ru/?partner=YOUR_ID",
    "aliexpress": "https://aliexpress.ru/?partner=YOUR_ID",
    "kwork": "https://kwork.ru/?ref=YOUR_ID",
}

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

def can_claim_daily(user_id):
    row = get_user(user_id)
    if not row or not row[8]:
        return True
    last = datetime.strptime(row[8], '%Y-%m-%d')
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

def get_all_users():
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, total_earned, referrals_count, joined_date FROM users ORDER BY total_earned DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_earned) FROM users")
    total_earned = c.fetchone()[0] or 0
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    c.execute("SELECT SUM(referrals_count) FROM users")
    total_refs = c.fetchone()[0] or 0
    c.execute("SELECT SUM(clicks) FROM users")
    total_clicks = c.fetchone()[0] or 0
    conn.close()
    return total_users, total_earned, total_balance, total_refs, total_clicks

def get_top_users(limit=10):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT username, total_earned FROM users WHERE total_earned > 0 ORDER BY total_earned DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def admin_send_money(user_id, amount):
    update_balance(user_id, amount)
    return True

def admin_take_money(user_id, amount):
    row = get_user(user_id)
    if row and row[4] >= amount:
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    return False

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

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
        [InlineKeyboardButton("💸 Забрать деньги", callback_data="admin_take")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🎁 Бонус всем", callback_data="admin_bonus_all")],
        [InlineKeyboardButton("🎟 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton("💰 Изменить бонусы", callback_data="admin_bonus_settings")],
        [InlineKeyboardButton("📈 Топ пользователей", callback_data="admin_top")],
        [InlineKeyboardButton("⚡ Активации за день", callback_data="admin_daily_stats")],
        [InlineKeyboardButton("🗑 Очистить базу", callback_data="admin_clear_confirm")],
        [InlineKeyboardButton("🔒 Закрыть", callback_data="admin_close")]
    ])

def get_earn_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Ozon (кэшбэк 15%)", url=PARTNER_LINKS['ozon']),
         InlineKeyboardButton("👕 Wildberries (12%)", url=PARTNER_LINKS['wildberries'])],
        [InlineKeyboardButton("📦 AliExpress (10%)", url=PARTNER_LINKS['aliexpress']),
         InlineKeyboardButton("💼 Kwork (20%)", url=PARTNER_LINKS['kwork'])],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])

def admin_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад в админ-панель", callback_data="admin_back")]])

# ==================== ОСНОВНЫЕ ОБРАБОТЧИКИ ====================
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
    
    elif data == "daily":
        if can_claim_daily(uid):
            claim_daily(uid)
            query.edit_message_text(f"🎁 Ежедневный бонус получен!\n💰 +{DAILY_BONUS} ₽", reply_markup=main_keyboard(uid))
        else:
            query.edit_message_text("❌ Ты уже получал бонус сегодня.\n📅 Заходи завтра!", reply_markup=main_keyboard(uid))
    
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
    
    elif data == "stats":
        balance = row[4] if row else 0
        earned = row[5] if row else 0
        refs = row[6] if row else 0
        clicks = row[7] if row else 0
        joined = row[9] if row else "—"
        total_users, total_earned_all, _, _, _ = get_stats()
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
    
    elif data == "earn":
        add_click(uid)
        query.edit_message_text(
            "💰 <b>Дополнительный заработок</b>\n\n"
            "🔥 Переходи по ссылкам и зарабатывай:\n"
            "• Кэшбэк до 20% на покупках\n"
            "• Бонусы за регистрацию\n\n"
            "<i>Каждый переход увеличивает твой рейтинг!</i>",
            parse_mode="HTML",
            reply_markup=get_earn_keyboard()
        )
    
    elif data == "support":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Написать админу", url="https://t.me/mskvoru")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
        query.edit_message_text(
            "❓ <b>Поддержка</b>\n\n"
            "По всем вопросам нажми на кнопку ниже:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    elif data == "back":
        query.edit_message_text("🤝 Главное меню:", reply_markup=main_keyboard(uid))

# ==================== АДМИН-ПАНЕЛЬ ====================
def admin_login(update: Update, context):
    if not context.args:
        update.message.reply_text("🔐 <b>Вход в админ-панель</b>\n\nВведи пароль: /admin 1997", parse_mode="HTML")
        return
    if context.args[0] == ADMIN_PASSWORD:
        context.user_data['admin_logged_in'] = True
        keyboard = admin_keyboard()
        update.message.reply_text(
            "👑 <b>ДОБРО ПОЖАЛОВАТЬ В АДМИН-ПАНЕЛЬ!</b>\n\n"
            "Выбери действие:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        update.message.reply_text("❌ Неверный пароль! Доступ запрещён.")

def admin_callback_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    
    if not context.user_data.get('admin_logged_in', False):
        query.edit_message_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    
    # Выдать деньги
    if data == "admin_give":
        query.edit_message_text(
            "💰 <b>Выдать деньги</b>\n\n"
            "Введи команду:\n"
            "<code>/give user_id сумма</code>\n\n"
            "Пример: <code>/give 6127276408 100</code>",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Забрать деньги
    elif data == "admin_take":
        query.edit_message_text(
            "💸 <b>Забрать деньги</b>\n\n"
            "Введи команду:\n"
            "<code>/take user_id сумма</code>\n\n"
            "Пример: <code>/take 6127276408 50</code>",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Рассылка
    elif data == "admin_broadcast":
        query.edit_message_text(
            "📢 <b>Рассылка</b>\n\n"
            "Введи команду:\n"
            "<code>/broadcast текст</code>\n\n"
            "Пример: <code>/broadcast Всем привет!</code>",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Список пользователей
    elif data == "admin_users":
        users = get_all_users()
        if not users:
            query.edit_message_text("❌ Нет пользователей", reply_markup=admin_back_keyboard())
            return
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        for i, u in enumerate(users[:20], 1):
            text += f"{i}. @{u[1] or u[0]} | 💰 {u[2]:.2f} ₽ | 👥 {u[4]}\n"
        if len(users) > 20:
            text += f"\n... и ещё {len(users) - 20} пользователей"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_back_keyboard())
    
    # Статистика
    elif data == "admin_stats":
        total_users, total_earned, total_balance, total_refs, total_clicks = get_stats()
        text = (
            f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"👥 Всего рефералов: {total_refs}\n"
            f"💰 Всего заработали: {total_earned:.2f} ₽\n"
            f"💳 На балансе: {total_balance:.2f} ₽\n"
            f"🖱 Переходов: {total_clicks}"
        )
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_back_keyboard())
    
    # Бонус всем
    elif data == "admin_bonus_all":
        query.edit_message_text(
            "🎁 <b>Бонус всем пользователям</b>\n\n"
            "Введи команду:\n"
            "<code>/bonus_all сумма</code>\n\n"
            "Пример: <code>/bonus_all 10</code>",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Создать промокод
    elif data == "admin_create_promo":
        query.edit_message_text(
            "🎟 <b>Создать промокод</b>\n\n"
            "Введи команду:\n"
            "<code>/create_promo КОД сумма</code>\n\n"
            "Пример: <code>/create_promo SUPER2025 200</code>",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Изменить бонусы
    elif data == "admin_bonus_settings":
        query.edit_message_text(
            "⚙️ <b>Настройки бонусов</b>\n\n"
            "Введи команды:\n"
            "<code>/set_ref_bonus 20</code> - бонус за реферала\n"
            "<code>/set_daily_bonus 10</code> - ежедневный бонус\n"
            "<code>/set_min_withdraw 200</code> - мин. вывод",
            parse_mode="HTML",
            reply_markup=admin_back_keyboard()
        )
    
    # Топ пользователей
    elif data == "admin_top":
        top = get_top_users(10)
        if not top:
            query.edit_message_text("📈 Пока нет заработавших", reply_markup=admin_back_keyboard())
            return
        text = "📈 <b>ТОП ПОЛЬЗОВАТЕЛЕЙ ПО ЗАРАБОТКУ</b>\n\n"
        for i, (username, earned) in enumerate(top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💰"
            text += f"{medal} {i}. @{username or 'anon'} — {earned:.2f} ₽\n"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_back_keyboard())
    
    # Активность за день
    elif data == "admin_daily_stats":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM users WHERE last_daily = ?", (today,))
        daily_active = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE joined_date LIKE ?", (f"{today}%",))
        new_today = c.fetchone()[0]
        conn.close()
        text = (
            f"⚡ <b>АКТИВНОСТЬ ЗА СЕГОДНЯ</b>\n\n"
            f"📅 Дата: {today}\n"
            f"✅ Забрали бонус: {daily_active} чел.\n"
            f"🆕 Новых пользователей: {new_today} чел."
        )
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_back_keyboard())
    
    # Очистить базу (подтверждение)
    elif data == "admin_clear_confirm":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ДА, ОЧИСТИТЬ", callback_data="admin_clear_yes")],
            [InlineKeyboardButton("❌ НЕТ, НАЗАД", callback_data="admin_back")]
        ])
        query.edit_message_text(
            "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
            "Ты собираешься удалить ВСЕХ пользователей и ВСЮ статистику.\n"
            "Это действие необратимо!\n\n"
            "Ты уверен?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    elif data == "admin_clear_yes":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        init_db()
        query.edit_message_text("✅ База данных успешно очищена!", reply_markup=admin_back_keyboard())
    
    elif data == "admin_back":
        query.edit_message_text(
            "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыбери действие:",
            parse_mode="HTML",
            reply_markup=admin_keyboard()
        )
    
    elif data == "admin_close":
        context.user_data['admin_logged_in'] = False
        query.edit_message_text("👑 Админ-панель закрыта", reply_markup=main_keyboard(uid))

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

# ==================== АДМИН-КОМАНДЫ ====================
def give_command(update: Update, context):
    if not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        if admin_send_money(user_id, amount):
            update.message.reply_text(f"✅ Выдано {amount} ₽ пользователю {user_id}")
            context.bot.send_message(user_id, f"🎉 <b>Администратор начислил тебе {amount} ₽!</b>", parse_mode="HTML")
        else:
            update.message.reply_text("❌ Ошибка. Пользователь не найден.")
    except:
        update.message.reply_text("❌ Используй: /give user_id сумма")

def take_command(update: Update, context):
    if not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        if admin_take_money(user_id, amount):
            update.message.reply_text(f"✅ Забрано {amount} ₽ у пользователя {user_id}")
            context.bot.send_message(user_id, f"⚠️ <b>С твоего баланса списано {amount} ₽</b>", parse_mode="HTML")
        else:
            update.message.reply_text("❌ Ошибка. Недостаточно средств или пользователь не найден.")
    except:
        update.message.reply_text("❌ Используй: /take user_id сумма")

def broadcast_command(update: Update, context):
    if not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    if not context.args:
        update.message.reply_text("❌ Используй: /broadcast текст")
        return
    text = ' '.join(context.args)
    users = get_all_users()
    success = 0
    for user in users:
        try:
            context.bot.send_message(user[0], f"📢 <b>РАССЫЛКА ОТ АДМИНА</b>\n\n{text}", parse_mode="HTML")
            success += 1
        except:
            pass
    update.message.reply_text(f"✅ Рассылка отправлена {success} пользователям")

def bonus_all_command(update: Update, context):
    if not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    try:
        amount = float(context.args[0])
        users = get_all_users()
        success = 0
        for user in users:
            try:
                admin_send_money(user[0], amount)
                context.bot.send_message(user[0], f"🎁 <b>БОНУС ОТ АДМИНА!</b>\n\n💰 +{amount} ₽", parse_mode="HTML")
                success += 1
            except:
                pass
        update.message.reply_text(f"✅ Бонус {amount} ₽ отправлен {success} пользователям")
    except:
        update.message.reply_text("❌ Используй: /bonus_all сумма")

def create_promo_command(update: Update, context):
    if not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа. Введи пароль: /admin 1997")
        return
    try:
        code = context.args[0].upper()
        amount = float(context.args[1])
        PROMO_CODES[code] = amount
        update.message.reply_text(f"✅ Промокод {code} на {amount} ₽ создан!")
    except:
        update.message.reply_text("❌ Используй: /create_promo КОД сумма")

def id_command(update: Update, context):
    user_id = update.effective_user.id
    update.message.reply_text(f"🆔 <b>Твой ID:</b> <code>{user_id}</code>\n\nОтправь этот ID администратору.", parse_mode="HTML")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    
    # Пользовательские команды
    dp.add_handler(Command
