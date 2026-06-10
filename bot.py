import sqlite3
import random
import string
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408
ADMIN_PASSWORD = "1997"

# Настройки
DAILY_BONUS = 5
MIN_WITHDRAW = 200

# Задания (пустой список — задания добавляет админ)
TASKS = []

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  balance INTEGER DEFAULT 0,
                  total_earned INTEGER DEFAULT 0,
                  completed_tasks TEXT DEFAULT '',
                  last_daily TEXT,
                  joined_date TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_user(user_id, username):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, username, joined_date) VALUES (?,?,?)",
                  (user_id, username, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def update_balance(user_id, amount):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    c.execute("UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def mark_task_completed(user_id, task_id):
    row = get_user(user_id)
    completed = row[4] if row else ""
    if str(task_id) in completed.split(","):
        return False
    new_completed = f"{completed},{task_id}" if completed else str(task_id)
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET completed_tasks = ? WHERE user_id = ?", (new_completed, user_id))
    conn.commit()
    conn.close()
    return True

def is_task_completed(user_id, task_id):
    row = get_user(user_id)
    completed = row[4] if row else ""
    return str(task_id) in completed.split(",")

def get_completed_count(user_id):
    row = get_user(user_id)
    completed = row[4] if row else ""
    return len([x for x in completed.split(",") if x])

def can_claim_daily(user_id):
    row = get_user(user_id)
    if not row or not row[5]:
        return True
    last = datetime.strptime(row[5], '%Y-%m-%d')
    return datetime.now().date() > last.date()

def claim_daily(user_id):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, DAILY_BONUS)

def get_all_users():
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, total_earned FROM users")
    rows = c.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_earned) FROM users")
    total_earned = c.fetchone()[0] or 0
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    conn.close()
    return total_users, total_earned, total_balance

def admin_send_money(user_id, amount):
    update_balance(user_id, amount)
    return True

# ==================== ПРОВЕРКА ПОДПИСКИ ====================
def check_subscription(bot, user_id, channel_username):
    try:
        chat_member = bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user_id)
        status = chat_member.status
        return status in ["member", "administrator", "creator"]
    except:
        return False

# ==================== СОВРЕМЕННЫЕ КЛАВИАТУРЫ ====================
def get_main_keyboard():
    """Стильные кнопки с эмодзи и обрамлением"""
    keyboard = [
        [KeyboardButton("💎 МОЙ БАЛАНС 💎"), KeyboardButton("📋 ЗАРАБОТАТЬ 📋")],
        [KeyboardButton("🎁 БОНУС ДНЯ 🎁"), KeyboardButton("💸 ВЫВОД ДЕНЕГ 💸")],
        [KeyboardButton("📊 СТАТИСТИКА 📊"), KeyboardButton("❓ ПОДДЕРЖКА ❓")],
        [KeyboardButton("⚡ АДМИН ПАНЕЛЬ ⚡")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def tasks_keyboard(user_id):
    keyboard = []
    for task in TASKS:
        completed = is_task_completed(user_id, task["id"])
        status = "✅" if completed else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {task['name']} 💰 +{task['reward']} ₽", callback_data=f"task_{task['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ НАЗАД В МЕНЮ", callback_data="back_tasks")])
    return InlineKeyboardMarkup(keyboard)

def admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 ВЫДАТЬ ДЕНЬГИ", callback_data="admin_give")],
        [InlineKeyboardButton("📢 СДЕЛАТЬ РАССЫЛКУ", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 СПИСОК ЮЗЕРОВ", callback_data="admin_users")],
        [InlineKeyboardButton("📊 СТАТИСТИКА БОТА", callback_data="admin_stats")],
        [InlineKeyboardButton("🎁 БОНУС ВСЕМ", callback_data="admin_bonus_all")],
        [InlineKeyboardButton("📝 ДОБАВИТЬ ЗАДАНИЕ", callback_data="admin_add_task")],
        [InlineKeyboardButton("🔒 ЗАКРЫТЬ", callback_data="admin_close")]
    ])

# ==================== ОБРАБОТЧИКИ ====================
def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
    if not get_user(uid):
        create_user(uid, name)
        update_balance(uid, 10)
    
    welcome_text = f"""
🌟 <b>ДОБРО ПОЖАЛОВАТЬ В ПРОФИТ БОТА!</b> 🌟

┌─────────────────────────────────┐
│  🤖 <b>ПРОСТОЙ ЗАРАБОТОК ДЛЯ ВСЕХ</b>  │
└─────────────────────────────────┘

💰 <b>КАК ЗАРАБОТАТЬ:</b>
   ✅ Выполняй простые задания
   ✅ Забирай ежедневный бонус
   ✅ Выводи деньги от {MIN_WITHDRAW} ₽

🎁 <b>ТВОЙ БОНУС:</b>
   За регистрацию +10 ₽ на баланс!

┌─────────────────────────────────┐
│  👇 ВЫБИРАЙ ДЕЙСТВИЕ В МЕНЮ 👇   │
└─────────────────────────────────┘
"""
    
    update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

def handle_buttons(update: Update, context):
    text = update.message.text
    uid = update.effective_user.id
    row = get_user(uid)
    
    if text == "💎 МОЙ БАЛАНС 💎":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        msg = f"""
💎 <b>ТВОЙ ФИНАНСОВЫЙ ОТЧЁТ</b> 💎

┌─────────────────────────────────┐
│  💰 ДОСТУПНО: {balance} ₽           │
│  📈 ЗАРАБОТАНО: {earned} ₽          │
│  ✅ ЗАДАНИЙ: {tasks_done} шт.        │
│  ⚡ МИНИМУМ ВЫВОДА: {MIN_WITHDRAW} ₽   │
└─────────────────────────────────┘
"""
        update.message.reply_text(msg, parse_mode="HTML", reply_markup=get_main_keyboard())
    
    elif text == "📋 ЗАРАБОТАТЬ 📋":
        if not TASKS:
            update.message.reply_text(
                "📋 <b>ЗАДАНИЙ ПОКА НЕТ</b>\n\n"
                "Но они скоро появятся! 🔥\n"
                "Загляни позже 👇",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return
        update.message.reply_text(
            "📋 <b>ВЫБЕРИ ЗАДАНИЕ</b> 📋\n\n"
            "┌─────────────────────────────────┐\n"
            "│  ✅ Нажми на задание            │\n"
            "│  🔗 Перейди по ссылке           │\n"
            "│  👍 Подпишись / поставь лайк    │\n"
            "│  🔄 Вернись и нажми «Проверить» │\n"
            "└─────────────────────────────────┘\n\n"
            "✅ <b>Выполненные задания отмечены галочкой</b>",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    elif text == "🎁 БОНУС ДНЯ 🎁":
        if can_claim_daily(uid):
            claim_daily(uid)
            update.message.reply_text(
                f"🎁 <b>БОНУС ДНЯ ПОЛУЧЕН!</b> 🎁\n\n"
                f"┌─────────────────────────────────┐\n"
                f"│  💰 +{DAILY_BONUS} ₽ НА БАЛАНС      │\n"
                f"│  📅 ЗАВТРА БУДЕТ НОВЫЙ БОНУС!   │\n"
                f"└─────────────────────────────────┘",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        else:
            update.message.reply_text(
                "❌ <b>ТЫ УЖЕ ЗАБИРАЛ БОНУС</b> ❌\n\n"
                "┌─────────────────────────────────┐\n"
                "│  📅 ВОЗВРАЩАЙСЯ ЗАВТРА!        │\n"
                "│  🎁 ТЕБЯ БУДЕТ ЖДАТЬ НОВЫЙ      │\n"
                "│     БОНУС!                      │\n"
                "└─────────────────────────────────┘",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    
    elif text == "💸 ВЫВОД ДЕНЕГ 💸":
        balance = row[2] if row else 0
        if balance < MIN_WITHDRAW:
            update.message.reply_text(
                f"❌ <b>НЕ ХВАТАЕТ ДЛЯ ВЫВОДА</b> ❌\n\n"
                f"┌─────────────────────────────────┐\n"
                f"│  💰 ТВОЙ БАЛАНС: {balance} ₽        │\n"
                f"│  ⚡ НУЖНО: {MIN_WITHDRAW} ₽          │\n"
                f"│  📋 ВЫПОЛНЯЙ ЗАДАНИЯ И ЗАБИРАЙ   │\n"
                f"│     БОНУСЫ КАЖДЫЙ ДЕНЬ!         │\n"
                f"└─────────────────────────────────┘",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return
        update.message.reply_text(
            f"✅ <b>ЗАЯВКА НА ВЫВОД ОТПРАВЛЕНА!</b> ✅\n\n"
            f"┌─────────────────────────────────┐\n"
            f"│  💰 СУММА: {balance} ₽             │\n"
            f"│  ⏱ ОБРАБОТКА: ДО 24 ЧАСОВ      │\n"
            f"│  📝 АДМИН СВЯЖЕТСЯ С ТОБОЙ      │\n"
            f"└─────────────────────────────────┘\n\n"
            f"👨‍💻 <b>По вопросам:</b> @n1kolay0_0",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "📊 СТАТИСТИКА 📊":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        joined = row[6] if row else "—"
        total_users, total_earned, total_balance = get_stats()
        msg = f"""
📊 <b>ТВОЯ СТАТИСТИКА</b> 📊

┌─────────────────────────────────┐
│  💰 ЗАРАБОТАНО: {earned} ₽         │
│  💳 ДОСТУПНО: {balance} ₽          │
│  ✅ ЗАДАНИЙ: {tasks_done} шт.       │
│  📅 В СИСТЕМЕ С: {joined[:10]}     │
└─────────────────────────────────┘

🌟 <b>ОБЩАЯ СТАТИСТИКА БОТА</b> 🌟
┌─────────────────────────────────┐
│  👤 ЮЗЕРОВ: {total_users}          │
│  💰 ВСЕГО ЗАРАБОТАНО: {total_earned} ₽ │
└─────────────────────────────────┘
"""
        update.message.reply_text(msg, parse_mode="HTML", reply_markup=get_main_keyboard())
    
    elif text == "❓ ПОДДЕРЖКА ❓":
        update.message.reply_text(
            "❓ <b>ПОДДЕРЖКА И ПОМОЩЬ</b> ❓\n\n"
            "┌─────────────────────────────────┐\n"
            "│  📌 <b>ЧАСТЫЕ ВОПРОСЫ:</b>          │\n"
            "│  • КАК ВЫВЕСТИ ДЕНЬГИ?          │\n"
            "│  • НЕ ПРИШЁЛ БОНУС?              │\n"
            "│  • НЕ РАБОТАЕТ ЗАДАНИЕ?          │\n"
            "└─────────────────────────────────┘\n\n"
            "👨‍💻 <b>ПИШИ АДМИНУ:</b> @n1kolay0_0\n\n"
            "📌 <i>ОТВЕЧАЮ БЫСТРО, ОБРАЩАЙСЯ!</i>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "⚡ АДМИН ПАНЕЛЬ ⚡":
        update.message.reply_text(
            "🔐 <b>ВВЕДИТЕ ПАРОЛЬ ДЛЯ ВХОДА</b> 🔐\n\n"
            "┌─────────────────────────────────┐\n"
            "│  ⚡ ТОЛЬКО ДЛЯ АДМИНИСТРАТОРА   │\n"
            "│  🔒 ВВЕДИТЕ ПАРОЛЬ В ЧАТ        │\n"
            "└─────────────────────────────────┘",
            parse_mode="HTML"
        )
        context.user_data['awaiting_admin_password'] = True

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    
    if data.startswith("task_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        
        if is_task_completed(uid, task_id):
            query.edit_message_text(
                f"❌ <b>ЗАДАНИЕ УЖЕ ВЫПОЛНЕНО!</b> ❌\n\n"
                f"📌 {task['name']}\n"
                f"💰 НАГРАДА: {task['reward']} ₽ (УЖЕ ПОЛУЧЕНА)",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        channel_username = task['url'].replace("https://t.me/", "").replace("@", "")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПЕРЕЙТИ К ЗАДАНИЮ", url=task['url'])],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ВЫПОЛНЕНИЕ", callback_data=f"check_{task_id}")],
            [InlineKeyboardButton("◀️ НАЗАД", callback_data="back_tasks")]
        ])
        query.edit_message_text(
            f"📌 <b>{task['name']}</b>\n\n"
            f"💰 НАГРАДА: {task['reward']} ₽\n\n"
            f"📝 <b>ИНСТРУКЦИЯ:</b>\n"
            f"1️⃣ НАЖМИ «ПЕРЕЙТИ К ЗАДАНИЮ»\n"
            f"2️⃣ ПОДПИШИСЬ НА КАНАЛ/ГРУППУ\n"
            f"3️⃣ ВЕРНИСЬ И НАЖМИ «ПРОВЕРИТЬ»\n\n"
            f"⚡ <i>БОТ ПРОВЕРИТ ПОДПИСКУ АВТОМАТИЧЕСКИ!</i>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    elif data.startswith("check_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        
        if is_task_completed(uid, task_id):
            query.edit_message_text(
                f"❌ <b>НАГРАДА УЖЕ ВЫДАЧЕНА!</b>",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        channel_username = task['url'].replace("https://t.me/", "").replace("@", "")
        is_subscribed = check_subscription(context.bot, uid, channel_username)
        
        if not is_subscribed:
            query.edit_message_text(
                f"❌ <b>ТЫ НЕ ПОДПИСАЛСЯ!</b> ❌\n\n"
                f"📌 {task['name']}\n\n"
                f"🔗 <b>ПОДПИШИСЬ СНАЧАЛА:</b>\n{task['url']}\n\n"
                f"✅ ПОСЛЕ ПОДПИСКИ НАЖМИ «ПРОВЕРИТЬ» СНОВА",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        mark_task_completed(uid, task_id)
        update_balance(uid, task['reward'])
        
        query.edit_message_text(
            f"✅ <b>ЗАДАНИЕ ВЫПОЛНЕНО!</b> ✅\n\n"
            f"📌 {task['name']}\n"
            f"💰 НАЧИСЛЕНО: +{task['reward']} ₽\n\n"
            f"🎉 <b>СПАСИБО ЗА ПОДПИСКУ!</b>\n"
            f"🔥 ПРОДОЛЖАЙ ВЫПОЛНЯТЬ ЗАДАНИЯ!",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    elif data == "back_tasks":
        query.edit_message_text(
            "📋 <b>ВЫБЕРИ ЗАДАНИЕ</b> 📋\n\n"
            "✅ ВЫПОЛНЕННЫЕ — С ГАЛОЧКОЙ\n"
            "❌ НОВЫЕ — ЖДУТ ТЕБЯ!",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    # ==================== АДМИН-ПАНЕЛЬ ====================
    elif data == "admin_give":
        query.edit_message_text(
            "💎 <b>ВЫДАТЬ ДЕНЬГИ</b> 💎\n\n"
            "┌─────────────────────────────────┐\n"
            "│  КОМАНДА:                       │\n"
            "│  <code>/give ID СУММА</code>        │\n"
            "│                                 │\n"
            "│  ПРИМЕР:                        │\n"
            "│  <code>/give 6127276408 100</code> │\n"
            "└─────────────────────────────────┘",
            parse_mode="HTML"
        )
    elif data == "admin_broadcast":
        query.edit_message_text(
            "📢 <b>СДЕЛАТЬ РАССЫЛКУ</b> 📢\n\n"
            "┌─────────────────────────────────┐\n"
            "│  КОМАНДА:                       │\n"
            "│  <code>/broadcast ТЕКСТ</code>     │\n"
            "│                                 │\n"
            "│  ПРИМЕР:                        │\n"
            "│  <code>/broadcast ВСЕМ ПРИВЕТ!</code> │\n"
            "└─────────────────────────────────┘",
            parse_mode="HTML"
        )
    elif data == "admin_users":
        users = get_all_users()
        if not users:
            query.edit_message_text("Нет пользователей")
            return
        text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        for u in users[:20]:
            text += f"👤 @{u[1] or u[0]} | 💰 {u[2]} ₽\n"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_stats":
        total_users, total_earned, total_balance = get_stats()
        text = f"📊 <b>СТАТИСТИКА БОТА</b>\n\n👥 ЮЗЕРОВ: {total_users}\n💰 ЗАРАБОТАНО: {total_earned} ₽\n💳 НА БАЛАНСЕ: {total_balance} ₽"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_bonus_all":
        query.edit_message_text(
            "🎁 <b>БОНУС ВСЕМ ЮЗЕРАМ</b>\n\n"
            "<code>/bonus_all СУММА</code>\n\n"
            "ПРИМЕР: <code>/bonus_all 10</code>",
            parse_mode="HTML"
        )
    elif data == "admin_add_task":
        query.edit_message_text(
            "📝 <b>ДОБАВИТЬ ЗАДАНИЕ</b>\n\n"
            "<code>/add_task НАЗВАНИЕ | @USERNAME | НАГРАДА</code>\n\n"
            "ПРИМЕР:\n"
            "<code>/add_task Подпишись на канал | @n1kolay0_0 | 10</code>",
            parse_mode="HTML"
        )
    elif data == "admin_close":
        context.user_data['admin_logged_in'] = False
        query.edit_message_text("🔒 Админ-панель закрыта", reply_markup=get_main_keyboard())

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if context.user_data.get('awaiting_admin_password'):
        if text == ADMIN_PASSWORD:
            context.user_data['admin_logged_in'] = True
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text(
                "✅ <b>ДОСТУП РАЗРЕШЁН!</b> ✅\n\n"
                "┌─────────────────────────────────┐\n"
                "│  ⚡ ДОБРО ПОЖАЛОВАТЬ В         │\n"
                "│     АДМИН-ПАНЕЛЬ!              │\n"
                "└─────────────────────────────────┘",
                parse_mode="HTML",
                reply_markup=admin_inline_keyboard()
            )
        else:
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text(
                "❌ <b>НЕВЕРНЫЙ ПАРОЛЬ!</b> ❌\n\n"
                "┌─────────────────────────────────┐\n"
                "│  🔒 ДОСТУП ЗАПРЕЩЁН            │\n"
                "│  ⚡ ПОПРОБУЙ ЕЩЁ РАЗ            │\n"
                "└─────────────────────────────────┘",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        return

# ==================== АДМИН-КОМАНДЫ ====================
def give_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID and not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        admin_send_money(user_id, amount)
        update.message.reply_text(f"✅ Выдано {amount} ₽ пользователю {user_id}")
        try:
            context.bot.send_message(user_id, f"🎉 Администратор начислил тебе {amount} ₽!")
        except:
            pass
    except:
        update.message.reply_text("❌ Используй: /give ID сумма")

def broadcast_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID and not context.user_data.get('admin_logged_in', False):
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
    if update.effective_user.id != ADMIN_ID and not context.user_data.get('admin_logged_in', False):
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

def add_task_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID and not context.user_data.get('admin_logged_in', False):
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        text = ' '.join(context.args)
        parts = text.split('|')
        if len(parts) != 3:
            update.message.reply_text("❌ Используй: /add_task название | @username | награда")
            return
        name = parts[0].strip()
        channel_username = parts[1].strip().replace("@", "")
        reward = int(parts[2].strip())
        url = f"https://t.me/{channel_username}"
        new_id = max([t["id"] for t in TASKS], default=0) + 1
        TASKS.append({"id": new_id, "name": name, "url": url, "reward": reward})
        update.message.reply_text(f"✅ Задание добавлено!\n\n{name}\n🔗 {url}\n💰 {reward} ₽")
    except:
        update.message.reply_text("❌ Ошибка. Используй: /add_task название | @username | награда")

def id_command(update: Update, context):
    update.message.reply_text(f"🆔 <b>Твой ID:</b> <code>{update.effective_user.id}</code>", parse_mode="HTML")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("id", id_command))
    dp.add_handler(CommandHandler("give", give_command))
    dp.add_handler(CommandHandler("broadcast", broadcast_command))
    dp.add_handler(CommandHandler("bonus_all", bonus_all_command))
    dp.add_handler(CommandHandler("add_task", add_task_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_buttons))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text, handle_message))
    
    updater.start_polling()
    print("🚀 Бот с современным дизайном запущен!")
    updater.idle()
