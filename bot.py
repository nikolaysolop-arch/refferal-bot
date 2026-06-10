import sqlite3
import random
import string
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

# ==================== КОНФИГ ====================
BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408
ADMIN_PASSWORD = "1997"  # Пароль для входа в админ-панель

REFERRAL_REWARD = 15
REFERRED_REWARD = 10
DAILY_BONUS = 5
MIN_WITHDRAW = 100

PROMO_CODES = {
    "START2025": 50,
    "BONUS100": 100,
    "FRIEND2025": 75
}

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
                  balance INTEGER DEFAULT 0,
                  total_earned INTEGER DEFAULT 0,
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

def get_all_users():
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, total_earned, referrals_count FROM users ORDER BY total_earned DESC")
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
    conn.close()
    return total_users, total_earned, total_balance, total_refs

def admin_send_money(user_id, amount):
    update_balance(user_id, amount)
    return True

def admin_take_money(user_id, amount):
    row = get_user(user_id)
    if row and row[3] >= amount:
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
    balance = row[3] if row else 0
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💰 Баланс: {balance} ₽", callback_data="balance")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referrals"), InlineKeyboardButton("🔗 Моя ссылка", callback_data="my_link")],
        [InlineKeyboardButton("🏆 Топ рефералов", callback_data="top")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily"), InlineKeyboardButton("🎟 Промокод", callback_data="promo")],
        [InlineKeyboardButton("💸 Вывести деньги", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("❓ Поддержка", callback_data="support")],
        [InlineKeyboardButton("🔐 Админ-панель", callback_data="admin_login")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
        [InlineKeyboardButton("💸 Забрать деньги", callback_data="admin_take")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🎁 Бонус всем", callback_data="admin_bonus_all")],
        [InlineKeyboardButton("🎟 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton("🔙 Закрыть", callback_data="admin_close")]
    ])

# ==================== ОБРАБОТЧИКИ ====================
def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
    # Реферальный код
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
        "🤝 <b>РЕФЕРАЛЬНЫЙ БОТ</b>\n\n"
        f"🔥 За каждого друга: +{REFERRAL_REWARD} ₽\n"
        f"🎁 Другу бонус: +{REFERRED_REWARD} ₽\n"
        f"📅 Ежедневный бонус: +{DAILY_BONUS} ₽\n\n"
        f"💎 Твой код: <code>{get_user(uid)[4]}</code>\n\n"
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
        query.edit_message_text(
            f"💰 <b>Твой баланс</b>\n\n"
            f"💵 Доступно: {row[3]} ₽\n"
            f"📈 Заработано всего: {row[4]} ₽\n"
            f"👥 Приглашено: {row[5]}\n\n"
            f"⚡ Минимум вывода: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    elif data == "my_link":
        code = row[4]
        bot_info = context.bot.get_me()
        url = f"https://t.me/{bot_info.username}?start={code}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={url}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ])
        query.edit_message_text(
            f"🔗 <b>Твоя ссылка</b>\n\n<code>{url}</code>\n\nПриглашай друзей!",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    elif data == "referrals":
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE referrer_id = ?", (uid,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            query.edit_message_text("👥 У тебя пока нет рефералов.", reply_markup=main_keyboard(uid))
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
            query.edit_message_text("🏆 Пока нет рефералов в топе.", reply_markup=main_keyboard(uid))
        else:
            text = "🏆 <b>Топ рефералов</b>\n\n"
            for i, (username, count) in enumerate(rows, 1):
                text += f"{i}. @{username or 'anon'} — {count} рефералов\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=main_keyboard(uid))
    elif data == "daily":
        if can_claim_daily(uid):
            claim_daily(uid)
            query.edit_message_text(f"🎁 Ежедневный бонус +{DAILY_BONUS} ₽", reply_markup=main_keyboard(uid))
        else:
            query.edit_message_text("❌ Бонус уже получен сегодня. Заходи завтра!", reply_markup=main_keyboard(uid))
    elif data == "promo":
        query.edit_message_text(
            "🎟 <b>Введи промокод</b>\n\n"
            "Доступные:\nSTART2025 (50₽), BONUS100 (100₽), FRIEND2025 (75₽)\n\n"
            "Напиши код в чат:",
            parse_mode="HTML"
        )
        context.user_data['awaiting_promo'] = True
    elif data == "withdraw":
        if row[3] < MIN_WITHDRAW:
            query.answer(f"❌ Минимум {MIN_WITHDRAW} ₽. У тебя {row[3]} ₽", show_alert=True)
            return
        query.edit_message_text(
            f"✅ <b>Заявка отправлена!</b>\n\nСумма: {row[3]} ₽\nАдмин свяжется с тобой.",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    elif data == "stats":
        total_users, total_earned, total_balance, total_refs = get_stats()
        query.edit_message_text(
            f"📊 <b>Твоя статистика</b>\n\n"
            f"👥 Рефералов: {row[5]}\n"
            f"💰 Заработано: {row[4]} ₽\n"
            f"💳 Доступно: {row[3]} ₽\n\n"
            f"📈 <b>Общая статистика</b>\n"
            f"👤 Пользователей: {total_users}\n"
            f"💰 Всего заработано: {total_earned} ₽",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    elif data == "support":
        query.edit_message_text(
            "❓ <b>Поддержка</b>\n\nСвяжись с админом: @mskvoru",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
    elif data == "admin_login":
        query.edit_message_text("🔐 <b>Введите пароль:</b>", parse_mode="HTML")
        context.user_data['awaiting_admin_password'] = True
    elif data == "back":
        query.edit_message_text("Главное меню:", reply_markup=main_keyboard(uid))
    elif data.startswith("admin_"):
        if not context.user_data.get('admin_logged_in', False):
            query.edit_message_text("❌ Нет доступа. Войдите в админ-панель.", reply_markup=main_keyboard(uid))
            return
        
        if data == "admin_give":
            query.edit_message_text("💰 Введи: /give ID сумма\nПример: /give 6127276408 100", parse_mode="HTML")
        elif data == "admin_take":
            query.edit_message_text("💸 Введи: /take ID сумма\nПример: /take 6127276408 50", parse_mode="HTML")
        elif data == "admin_broadcast":
            query.edit_message_text("📢 Введи: /broadcast текст", parse_mode="HTML")
        elif data == "admin_users":
            users = get_all_users()
            if not users:
                query.edit_message_text("Нет пользователей")
                return
            text = "👥 <b>Пользователи:</b>\n\n"
            for u in users[:20]:
                text += f"@{u[1] or u[0]} | 💰 {u[2]} ₽ | 👥 {u[4]}\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
        elif data == "admin_stats":
            total_users, total_earned, total_balance, total_refs = get_stats()
            text = f"📊 Статистика:\n👥 {total_users} юзеров\n💰 Заработано: {total_earned} ₽\n💳 На балансе: {total_balance} ₽\n👥 Рефералов: {total_refs}"
            query.edit_message_text(text, reply_markup=admin_keyboard())
        elif data == "admin_bonus_all":
            query.edit_message_text("🎁 Введи: /bonus_all сумма", parse_mode="HTML")
        elif data == "admin_create_promo":
            query.edit_message_text("🎟 Введи: /create_promo КОД сумма\nПример: /create_promo SUPER2025 200", parse_mode="HTML")
        elif data == "admin_close":
            context.user_data['admin_logged_in'] = False
            query.edit_message_text("Админ-панель закрыта", reply_markup=main_keyboard(uid))

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Проверка пароля админа
    if context.user_data.get('awaiting_admin_password'):
        if text == ADMIN_PASSWORD:
            context.user_data['admin_logged_in'] = True
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text("✅ Доступ разрешён!", reply_markup=admin_keyboard())
        else:
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text("❌ Неверный пароль!", reply_markup=main_keyboard(user_id))
        return
    
    # Промокоды
    if context.user_data.get('awaiting_promo'):
        code = text.upper()
        success, amount = apply_promo(user_id, code)
        if success:
            update.message.reply_text(f"✅ Промокод активирован! +{amount} ₽", reply_markup=main_keyboard(user_id))
        else:
            update.message.reply_text(f"❌ Неверный промокод: {code}", reply_markup=main_keyboard(user_id))
        context.user_data['awaiting_promo'] = False

# ==================== АДМИН-КОМАНДЫ ====================
def give_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        admin_send_money(user_id, amount)
        update.message.reply_text(f"✅ Выдано {amount} ₽ пользователю {user_id}")
        context.bot.send_message(user_id, f"🎉 Админ начислил тебе {amount} ₽!")
    except:
        update.message.reply_text("❌ Используй: /give ID сумма")

def take_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        if admin_take_money(user_id, amount):
            update.message.reply_text(f"✅ Забрано {amount} ₽ у {user_id}")
            context.bot.send_message(user_id, f"⚠️ С твоего баланса списано {amount} ₽")
        else:
            update.message.reply_text("❌ Недостаточно средств")
    except:
        update.message.reply_text("❌ Используй: /take ID сумма")

def broadcast_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    if not context.args:
        update.message.reply_text("❌ Используй: /broadcast текст")
        return
    text = ' '.join(context.args)
    users = get_all_users()
    success = 0
    for user in users:
        try:
            context.bot.send_message(user[0], f"📢 {text}")
            success += 1
        except:
            pass
    update.message.reply_text(f"✅ Рассылка отправлена {success} пользователям")

def bonus_all_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        amount = int(context.args[0])
        users = get_all_users()
        success = 0
        for user in users:
            try:
                admin_send_money(user[0], amount)
                context.bot.send_message(user[0], f"🎁 Бонус всем! +{amount} ₽")
                success += 1
            except:
                pass
        update.message.reply_text(f"✅ Бонус {amount} ₽ отправлен {success} пользователям")
    except:
        update.message.reply_text("❌ Используй: /bonus_all сумма")

def create_promo_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        code = context.args[0].upper()
        amount = int(context.args[1])
        PROMO_CODES[code] = amount
        update.message.reply_text(f"✅ Промокод {code} на {amount} ₽ создан!")
    except:
        update.message.reply_text("❌ Используй: /create_promo КОД сумма")

def id_command(update: Update, context):
    update.message.reply_text(f"🆔 Твой ID: {update.effective_user.id}")

if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("id", id_command))
    dp.add_handler(CommandHandler("give", give_command))
    dp.add_handler(CommandHandler("take", take_command))
    dp.add_handler(CommandHandler("broadcast", broadcast_command))
    dp.add_handler(CommandHandler("bonus_all", bonus_all_command))
    dp.add_handler(CommandHandler("create_promo", create_promo_command))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text, handle_message))
    
    updater.start_polling()
    print("Бот с полным функционалом запущен!")
    updater.idle()
