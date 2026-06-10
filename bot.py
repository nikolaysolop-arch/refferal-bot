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

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    """Кнопки снизу (ReplyKeyboard)"""
    keyboard = [
        [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Выполнить задания")],
        [KeyboardButton("🎁 Ежедневный бонус"), KeyboardButton("💸 Вывести деньги")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("❓ Поддержка")],
        [KeyboardButton("🔐 Админ-панель")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def tasks_keyboard(user_id):
    keyboard = []
    for task in TASKS:
        completed = is_task_completed(user_id, task["id"])
        status = "✅" if completed else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {task['name']} (+{task['reward']} ₽)", callback_data=f"task_{task['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_tasks")])
    return InlineKeyboardMarkup(keyboard)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🎁 Бонус всем", callback_data="admin_bonus_all")],
        [InlineKeyboardButton("📝 Добавить задание", callback_data="admin_add_task")],
        [InlineKeyboardButton("🔙 Закрыть", callback_data="admin_close")]
    ])

# ==================== ОБРАБОТЧИКИ ====================
def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
    if not get_user(uid):
        create_user(uid, name)
        update_balance(uid, 10)
    
    welcome_text = f"""
✨ <b>ДОБРО ПОЖАЛОВАТЬ, {name}!</b> ✨

🤖 <b>Это бот для заработка на заданиях!</b>

💰 <b>КАК ЗАРАБОТАТЬ:</b>
• Выполняй простые задания (подписки)
• Забирай ежедневный бонус
• Выводи деньги от {MIN_WITHDRAW} ₽

🎁 <b>БОНУС:</b>
За регистрацию ты получил 10 ₽ на баланс!

👇 <b>Нажимай на кнопки внизу и зарабатывай!</b>
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
    
    if text == "💰 Баланс":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        update.message.reply_text(
            f"💰 <b>ТВОЙ БАЛАНС</b>\n\n"
            f"💵 Доступно: {balance} ₽\n"
            f"📈 Заработано всего: {earned} ₽\n"
            f"✅ Выполнено заданий: {tasks_done}\n\n"
            f"⚡ Минимум вывода: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "📋 Выполнить задания":
        if not TASKS:
            update.message.reply_text(
                "📋 <b>ЗАДАНИЙ ПОКА НЕТ</b>\n\n"
                "Задания скоро появятся. Загляни позже!",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return
        update.message.reply_text(
            "📋 <b>ВЫБЕРИ ЗАДАНИЕ</b>\n\n"
            "Нажми на задание → перейди по ссылке → подпишись → вернись и нажми «Проверить»\n\n"
            "✅ <b>Выполненные задания отмечены галочкой</b>",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    elif text == "🎁 Ежедневный бонус":
        if can_claim_daily(uid):
            claim_daily(uid)
            update.message.reply_text(
                f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС ПОЛУЧЕН!</b>\n\n"
                f"💰 +{DAILY_BONUS} ₽\n\n"
                f"📅 Заходи завтра снова!",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        else:
            update.message.reply_text(
                "❌ <b>Ты уже получал бонус сегодня!</b>\n\n"
                "📅 Возвращайся завтра.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    
    elif text == "💸 Вывести деньги":
        balance = row[2] if row else 0
        if balance < MIN_WITHDRAW:
            update.message.reply_text(
                f"❌ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n\n"
                f"💰 Твой баланс: {balance} ₽\n"
                f"⚡ Минимальная сумма вывода: {MIN_WITHDRAW} ₽\n\n"
                f"📋 Выполняй задания, чтобы накопить нужную сумму!",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return
        update.message.reply_text(
            f"✅ <b>ЗАЯВКА НА ВЫВОД ОТПРАВЛЕНА!</b>\n\n"
            f"💰 Сумма: {balance} ₽\n"
            f"⚡ Минимум вывода: {MIN_WITHDRAW} ₽\n\n"
            f"📝 Администратор свяжется с тобой в ближайшее время.\n\n"
            f"💬 Для ускорения напиши админу: @n1kolay0_0",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "📊 Статистика":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        joined = row[6] if row else "—"
        total_users, total_earned, total_balance = get_stats()
        update.message.reply_text(
            f"📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
            f"💰 Заработано: {earned} ₽\n"
            f"💳 Доступно: {balance} ₽\n"
            f"✅ Выполнено заданий: {tasks_done}\n"
            f"📅 В системе с: {joined[:10]}\n\n"
            f"📈 <b>ОБЩАЯ СТАТИСТИКА</b>\n"
            f"👤 Пользователей: {total_users}\n"
            f"💰 Всего заработано: {total_earned} ₽",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "❓ Поддержка":
        update.message.reply_text(
            "❓ <b>ПОДДЕРЖКА</b>\n\n"
            "По всем вопросам пиши админу:\n"
            "👨‍💻 @n1kolay0_0",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "🔐 Админ-панель":
        update.message.reply_text(
            "🔐 <b>Введите пароль:</b>",
            parse_mode="HTML"
        )
        context.user_data['awaiting_admin_password'] = True

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    row = get_user(uid)
    
    if data.startswith("task_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        
        if is_task_completed(uid, task_id):
            query.edit_message_text(
                f"❌ <b>Ты уже выполнил это задание!</b>\n\n"
                f"{task['name']}\n"
                f"💰 Награда: {task['reward']} ₽ (уже получена)",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        channel_username = task['url'].replace("https://t.me/", "").replace("@", "")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПЕРЕЙТИ К ЗАДАНИЮ", url=task['url'])],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ВЫПОЛНЕНИЕ", callback_data=f"check_{task_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_tasks")]
        ])
        query.edit_message_text(
            f"📌 <b>{task['name']}</b>\n\n"
            f"💰 Награда: {task['reward']} ₽\n\n"
            f"📝 <b>Инструкция:</b>\n"
            f"1. Нажми «Перейти к заданию»\n"
            f"2. Подпишись на канал/группу\n"
            f"3. Вернись в бота и нажми «Проверить выполнение»\n\n"
            f"⚠️ <i>Бот автоматически проверит подписку!</i>",
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
                f"❌ <b>Ты уже получил награду за это задание!</b>",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        channel_username = task['url'].replace("https://t.me/", "").replace("@", "")
        is_subscribed = check_subscription(context.bot, uid, channel_username)
        
        if not is_subscribed:
            query.edit_message_text(
                f"❌ <b>Ты не подписан!</b>\n\n"
                f"📌 {task['name']}\n\n"
                f"🔗 <b>Пожалуйста, подпишись сначала:</b>\n{task['url']}\n\n"
                f"После подписки нажми «Проверить» снова.",
                parse_mode="HTML",
                reply_markup=tasks_keyboard(uid)
            )
            return
        
        mark_task_completed(uid, task_id)
        update_balance(uid, task['reward'])
        
        query.edit_message_text(
            f"✅ <b>ЗАДАНИЕ ВЫПОЛНЕНО!</b>\n\n"
            f"📌 {task['name']}\n"
            f"💰 Начислено: +{task['reward']} ₽\n\n"
            f"🎉 Спасибо за подписку! Продолжай выполнять задания!",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    elif data == "back_tasks":
        query.edit_message_text(
            "📋 <b>ВЫБЕРИ ЗАДАНИЕ</b>",
            parse_mode="HTML",
            reply_markup=tasks_keyboard(uid)
        )
    
    # ==================== АДМИН-ПАНЕЛЬ ====================
    elif data.startswith("admin_"):
        if not context.user_data.get('admin_logged_in', False):
            query.edit_message_text("❌ Нет доступа.")
            return
        
        if data == "admin_give":
            query.edit_message_text(
                "💰 <b>Выдать деньги</b>\n\n"
                "<code>/give ID сумма</code>\n\n"
                "Пример: <code>/give 6127276408 100</code>",
                parse_mode="HTML"
            )
        elif data == "admin_broadcast":
            query.edit_message_text(
                "📢 <b>Рассылка</b>\n\n"
                "<code>/broadcast текст</code>",
                parse_mode="HTML"
            )
        elif data == "admin_users":
            users = get_all_users()
            if not users:
                query.edit_message_text("Нет пользователей")
                return
            text = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n"
            for u in users[:20]:
                text += f"@{u[1] or u[0]} | 💰 {u[2]} ₽\n"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
        elif data == "admin_stats":
            total_users, total_earned, total_balance = get_stats()
            text = f"📊 <b>СТАТИСТИКА</b>\n\n👥 {total_users} юзеров\n💰 Заработано: {total_earned} ₽\n💳 На балансе: {total_balance} ₽"
            query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
        elif data == "admin_bonus_all":
            query.edit_message_text(
                "🎁 <b>Бонус всем</b>\n\n"
                "<code>/bonus_all сумма</code>",
                parse_mode="HTML"
            )
        elif data == "admin_add_task":
            query.edit_message_text(
                "📝 <b>Добавить задание</b>\n\n"
                "<code>/add_task название | @username_канала | награда</code>\n\n"
                "Пример:\n"
                "<code>/add_task Подпишись на канал | @example | 10</code>",
                parse_mode="HTML"
            )
        elif data == "admin_close":
            context.user_data['admin_logged_in'] = False
            query.edit_message_text("🔐 Админ-панель закрыта")

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if context.user_data.get('awaiting_admin_password'):
        if text == ADMIN_PASSWORD:
            context.user_data['admin_logged_in'] = True
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text("✅ Доступ разрешён!", reply_markup=admin_keyboard())
        else:
            context.user_data['awaiting_admin_password'] = False
            update.message.reply_text("❌ Неверный пароль!", reply_markup=get_main_keyboard())
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
    print("🚀 Бот с постоянными кнопками запущен!")
    updater.idle()
