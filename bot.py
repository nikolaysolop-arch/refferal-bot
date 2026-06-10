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

DAILY_BONUS = 5
MIN_WITHDRAW = 200
REQUIRED_CHANNEL = "@prof1t_77"

TASKS = []

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

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

def check_subscription(bot, user_id, channel_username):
    if user_id == ADMIN_ID:
        return True
    try:
        chat_member = bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        status = chat_member.status
        return status in ["member", "administrator", "creator"]
    except:
        return False

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("💰 Баланс"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎁 Бонус"), KeyboardButton("💸 Вывод")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("⚡ Админ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def tasks_keyboard(user_id):
    keyboard = []
    for task in TASKS:
        completed = is_task_completed(user_id, task["id"])
        status = "✅" if completed else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {task['name']} | +{task['reward']} ₽", callback_data=f"task_{task['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_tasks")])
    return InlineKeyboardMarkup(keyboard)

def admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Выдать деньги", callback_data="admin_give")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Список юзеров", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🎁 Бонус всем", callback_data="admin_bonus_all")],
        [InlineKeyboardButton("📝 Добавить задание", callback_data="admin_add_task")],
        [InlineKeyboardButton("🔒 Закрыть", callback_data="admin_close")]
    ])

def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    
    if not check_subscription(context.bot, uid, REQUIRED_CHANNEL):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
        ])
        update.message.reply_text(
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\n"
            f"Для использования бота необходимо подписаться на наш канал.\n\n"
            f"👇 <b>Нажми на кнопку ниже и подпишись!</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    if not get_user(uid):
        create_user(uid, name)
        update_balance(uid, 10)
    
    welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {MIN_WITHDRAW} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию

👇 <b>Нажми «Задания» и начни зарабатывать!</b>"""
    
    update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

def check_subscription_callback(update: Update, context):
    query = update.callback_query
    query.answer()
    uid = query.from_user.id
    name = query.from_user.username or query.from_user.first_name
    
    if check_subscription(context.bot, uid, REQUIRED_CHANNEL):
        if not get_user(uid):
            create_user(uid, name)
            update_balance(uid, 10)
        
        welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {MIN_WITHDRAW} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию

👇 <b>Нажми «Задания» и начни зарабатывать!</b>"""
        
        query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
        ])
        query.edit_message_text(
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\n"
            f"Ты ещё не подписан на канал!\n\n"
            f"👇 <b>Подпишись и нажми «Проверить подписку».</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

def handle_buttons(update: Update, context):
    text = update.message.text
    uid = update.effective_user.id
    
    if not check_subscription(context.bot, uid, REQUIRED_CHANNEL):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
        ])
        update.message.reply_text(
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\n"
            f"Для использования бота необходимо подписаться на канал.\n\n"
            f"👇 <b>Подпишись и нажми «Проверить подписку».</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    row = get_user(uid)
    
    if text == "💰 Баланс":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        update.message.reply_text(
            f"💰 <b>Твой баланс</b>\n\n"
            f"Доступно: {balance} ₽\n"
            f"Заработано: {earned} ₽\n"
            f"Выполнено заданий: {tasks_done}\n\n"
            f"⚡ Минимум вывода: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "📋 Задания":
        if not TASKS:
            update.message.reply_text("📋 <b>Заданий пока нет.</b>\n\nОни скоро появятся. Загляни позже!", parse_mode="HTML", reply_markup=get_main_keyboard())
            return
        update.message.reply_text("📋 <b>Доступные задания</b>\n\nНажми на задание → перейди по ссылке → подпишись → нажми «Проверить»", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
    
    elif text == "🎁 Бонус":
        if can_claim_daily(uid):
            claim_daily(uid)
            update.message.reply_text(f"🎁 <b>Бонус получен!</b>\n\n+{DAILY_BONUS} ₽ на баланс\n\nЗаходи завтра снова.", parse_mode="HTML", reply_markup=get_main_keyboard())
        else:
            update.message.reply_text("❌ <b>Ты уже получал бонус сегодня</b>\n\nВозвращайся завтра.", parse_mode="HTML", reply_markup=get_main_keyboard())
    
    elif text == "💸 Вывод":
        balance = row[2] if row else 0
        if balance < MIN_WITHDRAW:
            update.message.reply_text(f"❌ <b>Недостаточно средств</b>\n\nТвой баланс: {balance} ₽\nНужно: {MIN_WITHDRAW} ₽\n\nВыполняй задания, чтобы накопить нужную сумму.", parse_mode="HTML", reply_markup=get_main_keyboard())
            return
        update.message.reply_text(f"✅ <b>Заявка на вывод отправлена</b>\n\nСумма: {balance} ₽\n\nАдминистратор свяжется с тобой.\n\nПо вопросам: @n1kolay0_0", parse_mode="HTML", reply_markup=get_main_keyboard())
    
    elif text == "📊 Статистика":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        joined = row[6] if row else "—"
        total_users, total_earned, total_balance = get_stats()
        update.message.reply_text(
            f"📊 <b>Твоя статистика</b>\n\n"
            f"💰 Заработано: {earned} ₽\n"
            f"💳 Доступно: {balance} ₽\n"
            f"✅ Заданий: {tasks_done}\n"
            f"📅 В системе с: {joined[:10]}\n\n"
            f"📈 <b>Общая статистика</b>\n"
            f"👤 Пользователей: {total_users}\n"
            f"💰 Всего заработано: {total_earned} ₽",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "❓ Помощь":
        update.message.reply_text("❓ <b>Помощь</b>\n\nПо всем вопросам пиши админу:\n👨‍💻 @n1kolay0_0\n\nОбычно отвечаю в течение нескольких часов.", parse_mode="HTML", reply_markup=get_main_keyboard())
    
    elif text == "⚡ Админ":
        if uid != ADMIN_ID:
            update.message.reply_text("❌ <b>Нет доступа</b>\n\nЭта панель только для администратора.", parse_mode="HTML", reply_markup=get_main_keyboard())
            return
        # Сразу открываем админ-панель без пароля
        update.message.reply_text(
            "✅ <b>АДМИН-ПАНЕЛЬ</b>\n\nДобро пожаловать!",
            parse_mode="HTML",
            reply_markup=admin_inline_keyboard()
        )

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    
    if data == "check_sub":
        if check_subscription(context.bot, uid, REQUIRED_CHANNEL):
            name = query.from_user.username or query.from_user.first_name
            if not get_user(uid):
                create_user(uid, name)
                update_balance(uid, 10)
            
            welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {MIN_WITHDRAW} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию

👇 <b>Нажми «Задания» и начни зарабатывать!</b>"""
            
            query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
                [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
            ])
            query.edit_message_text(
                f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\n"
                f"Ты ещё не подписан на канал!\n\n"
                f"👇 <b>Подпишись и нажми «Проверить подписку».</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        return
    
    if data.startswith("task_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        
        if is_task_completed(uid, task_id):
            query.edit_message_text(f"❌ <b>Задание уже выполнено</b>\n\n{task['name']}\nНаграда: {task['reward']} ₽ (уже получена)", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Перейти к заданию", url=task['url'])],
            [InlineKeyboardButton("✅ Проверить", callback_data=f"check_{task_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_tasks")]
        ])
        query.edit_message_text(f"📌 <b>{task['name']}</b>\n\n💰 Награда: {task['reward']} ₽\n\n📝 Инструкция:\n1. Нажми «Перейти к заданию»\n2. Подпишись на канал/группу\n3. Вернись и нажми «Проверить»\n\n⚡ Бот проверит подписку автоматически.", parse_mode="HTML", reply_markup=keyboard)
    
    elif data.startswith("check_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        
        if is_task_completed(uid, task_id):
            query.edit_message_text("❌ <b>Награда уже выдана</b>", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
            return
        
        channel_username = task['url'].replace("https://t.me/", "").replace("@", "")
        is_subscribed = check_subscription(context.bot, uid, f"@{channel_username}")
        
        if not is_subscribed:
            query.edit_message_text(f"❌ <b>Ты не подписан</b>\n\n📌 {task['name']}\n\nПодпишись сначала: {task['url']}\n\nПосле подписки нажми «Проверить» снова.", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
            return
        
        mark_task_completed(uid, task_id)
        update_balance(uid, task['reward'])
        
        query.edit_message_text(f"✅ <b>Задание выполнено!</b>\n\n📌 {task['name']}\n💰 Начислено: +{task['reward']} ₽\n\n🎉 Спасибо! Продолжай выполнять задания.", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
    
    elif data == "back_tasks":
        query.edit_message_text("📋 <b>Доступные задания</b>", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
    
    # Админ-панель (без пароля, только по ID)
    elif data == "admin_give":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        query.edit_message_text("💰 <b>Выдать деньги</b>\n\n/give ID сумма\n\nПример: /give 6127276408 100", parse_mode="HTML")
    elif data == "admin_broadcast":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        query.edit_message_text("📢 <b>Рассылка</b>\n\n/broadcast текст\n\nПример: /broadcast Всем привет!", parse_mode="HTML")
    elif data == "admin_users":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        users = get_all_users()
        if not users:
            query.edit_message_text("Нет пользователей")
            return
        text = "👥 <b>Список пользователей</b>\n\n"
        for u in users[:20]:
            text += f"@{u[1] or u[0]} | {u[2]} ₽\n"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_stats":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        total_users, total_earned, total_balance = get_stats()
        text = f"📊 <b>Статистика</b>\n\n👥 Пользователей: {total_users}\n💰 Заработано: {total_earned} ₽\n💳 На балансе: {total_balance} ₽"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_bonus_all":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        query.edit_message_text("🎁 <b>Бонус всем</b>\n\n/bonus_all сумма\n\nПример: /bonus_all 10", parse_mode="HTML")
    elif data == "admin_add_task":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        query.edit_message_text("📝 <b>Добавить задание</b>\n\n/add_task название | @username | награда\n\nПример:\n/add_task Подпишись на канал | @example | 10", parse_mode="HTML")
    elif data == "admin_close":
        if uid != ADMIN_ID:
            query.edit_message_text("❌ Нет доступа")
            return
        query.edit_message_text("🔒 Админ-панель закрыта", reply_markup=get_main_keyboard())

def handle_message(update: Update, context):
    # Эта функция больше не нужна для пароля, но оставим для других сообщений
    pass

def give_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
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

def add_task_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
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
        update.message.reply_text(f"✅ Задание добавлено!\n\n{name}\n{url}\n💰 {reward} ₽")
    except:
        update.message.reply_text("❌ Ошибка. Используй: /add_task название | @username | награда")

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
    dp.add_handler(CommandHandler("broadcast", broadcast_command))
    dp.add_handler(CommandHandler("bonus_all", bonus_all_command))
    dp.add_handler(CommandHandler("add_task", add_task_command))
    dp.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_buttons))
    dp.add_handler(CallbackQueryHandler(button_handler))
    
    updater.start_polling()
    print("Бот запущен!")
    updater.idle()
