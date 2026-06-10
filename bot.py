import sqlite3
import random
import string
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, PreCheckoutQueryHandler

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408
PROVIDER_TOKEN = "ВАШ_ТОКЕН_ПРОДАЙЦА"

REQUIRED_CHANNEL = "@prof1t_77"

NORMAL_TASK_REWARD = 10
NORMAL_DAILY_BONUS = 5
NORMAL_MIN_WITHDRAW = 200

PRO_TASK_REWARD = 20
PRO_DAILY_BONUS = 15
PRO_MIN_WITHDRAW = 100
PRO_PRICE_STARS = 100

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
                  joined_date TEXT,
                  pro_until TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  amount INTEGER,
                  method TEXT,
                  details TEXT,
                  status TEXT DEFAULT 'pending',
                  date TEXT)''')
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
    if amount > 0:
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
    is_pro = check_pro_status(user_id)
    bonus = PRO_DAILY_BONUS if is_pro else NORMAL_DAILY_BONUS
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, bonus)
    return bonus

def get_all_users():
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, total_earned, pro_until FROM users")
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

def check_pro_status(user_id):
    row = get_user(user_id)
    if not row or not row[7]:
        return False
    pro_until = datetime.strptime(row[7], '%Y-%m-%d')
    return datetime.now() < pro_until

def get_task_reward(user_id, base_reward):
    return base_reward * 2 if check_pro_status(user_id) else base_reward

def get_min_withdraw(user_id):
    return PRO_MIN_WITHDRAW if check_pro_status(user_id) else NORMAL_MIN_WITHDRAW

def activate_pro(user_id, days=30):
    new_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET pro_until = ? WHERE user_id = ?", (new_date, user_id))
    conn.commit()
    conn.close()

def deactivate_pro(user_id):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET pro_until = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def save_withdraw_request(user_id, username, amount, method, details):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO withdraw_requests (user_id, username, amount, method, details, date) VALUES (?,?,?,?,?,?)",
              (user_id, username, amount, method, details, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def get_pending_requests():
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, amount, method, details, date FROM withdraw_requests WHERE status = 'pending' ORDER BY date DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def complete_request(request_id):
    conn = sqlite3.connect('task_bot.db')
    c = conn.cursor()
    c.execute("UPDATE withdraw_requests SET status = 'completed' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def get_main_keyboard(user_id):
    row = get_user(user_id)
    balance = row[2] if row else 0
    is_pro = check_pro_status(user_id)
    pro_badge = " 👑 PRO" if is_pro else ""
    keyboard = [
        [KeyboardButton(f"💰 Баланс{pro_badge}"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🎁 Бонус"), KeyboardButton("💸 Вывод")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("💎 PRO Подписка"), KeyboardButton("⚡ Админ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def tasks_keyboard(user_id):
    keyboard = []
    for task in TASKS:
        completed = is_task_completed(user_id, task["id"])
        status = "✅" if completed else "❌"
        reward = get_task_reward(user_id, task["reward"])
        keyboard.append([InlineKeyboardButton(f"{status} {task['name']} | +{reward} ₽", callback_data=f"task_{task['id']}")])
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
        [InlineKeyboardButton("👑 Включить PRO", callback_data="admin_pro_on")],
        [InlineKeyboardButton("👑 Выключить PRO", callback_data="admin_pro_off")],
        [InlineKeyboardButton("💳 Заявки на вывод", callback_data="admin_withdraw_requests")],
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
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\nДля использования бота необходимо подписаться на наш канал.\n\n👇 <b>Нажми на кнопку ниже и подпишись!</b>",
            parse_mode="HTML", reply_markup=keyboard
        )
        return
    if not get_user(uid):
        create_user(uid, name)
        update_balance(uid, 10)
    is_pro = check_pro_status(uid)
    pro_text = "\n\n👑 У тебя PRO-подписка! Награды увеличены!" if is_pro else "\n\n💎 Оформи PRO-подписку за 100 Stars и получай увеличенные награды!"
    welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {get_min_withdraw(uid)} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию{pro_text}

👇 <b>Нажми на кнопки внизу и зарабатывай!</b>"""
    update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(uid))

def check_subscription_callback(update: Update, context):
    query = update.callback_query
    query.answer()
    uid = query.from_user.id
    name = query.from_user.username or query.from_user.first_name
    if check_subscription(context.bot, uid, REQUIRED_CHANNEL):
        if not get_user(uid):
            create_user(uid, name)
            update_balance(uid, 10)
        is_pro = check_pro_status(uid)
        pro_text = "\n\n👑 У тебя PRO-подписка! Награды увеличены!" if is_pro else "\n\n💎 Оформи PRO-подписку за 100 Stars и получай увеличенные награды!"
        welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {get_min_withdraw(uid)} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию{pro_text}

👇 <b>Нажми на кнопки внизу и зарабатывай!</b>"""
        query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(uid))
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
            [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
        ])
        query.edit_message_text(
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\nТы ещё не подписан на канал!\n\n👇 <b>Подпишись и нажми «Проверить подписку».</b>",
            parse_mode="HTML", reply_markup=keyboard
        )

def pro_payment(update: Update, context):
    uid = update.effective_user.id
    if check_pro_status(uid):
        update.message.reply_text("👑 У тебя уже активна PRO-подписка!", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
        return
    prices = [LabeledPrice(label="PRO-подписка на 30 дней", amount=PRO_PRICE_STARS)]
    try:
        update.message.reply_invoice(
            title="💎 PRO Подписка",
            description="Увеличенные награды + повышенный бонус + сниженный минимум вывода на 30 дней",
            payload="pro_subscription", provider_token=PROVIDER_TOKEN, currency="XTR",
            prices=prices, start_parameter="pro_sub", need_name=False, need_phone_number=False, need_email=False
        )
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка при оплате: {e}\n\nПроверь настройки платежей в BotFather.", parse_mode="HTML", reply_markup=get_main_keyboard(uid))

def pre_checkout(update: Update, context):
    query = update.pre_checkout_query
    query.answer(ok=True) if query.invoice_payload == "pro_subscription" else query.answer(ok=False, error_message="Что-то пошло не так")

def successful_payment(update: Update, context):
    uid = update.effective_user.id
    activate_pro(uid, 30)
    update.message.reply_text(
        "✅ <b>Поздравляю! PRO-подписка активирована на 30 дней!</b>\n\n"
        "👑 Теперь ты получаешь:\n• Увеличенные награды за задания (в 2 раза)\n"
        f"• Ежедневный бонус {PRO_DAILY_BONUS} ₽ (было {NORMAL_DAILY_BONUS})\n"
        f"• Минимум вывода {PRO_MIN_WITHDRAW} ₽ (было {NORMAL_MIN_WITHDRAW})\n\nСпасибо за поддержку! 🎉",
        parse_mode="HTML", reply_markup=get_main_keyboard(uid)
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
            f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\nДля использования бота необходимо подписаться на канал.\n\n👇 <b>Подпишись и нажми «Проверить подписку».</b>",
            parse_mode="HTML", reply_markup=keyboard
        )
        return
    row = get_user(uid)
    is_pro = check_pro_status(uid)
    pro_badge = " 👑" if is_pro else ""
    if text == f"💰 Баланс{pro_badge}" or text == "💰 Баланс":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        min_withdraw = get_min_withdraw(uid)
        update.message.reply_text(
            f"💰 <b>Твой баланс</b>{' 👑 PRO' if is_pro else ''}\n\nДоступно: {balance} ₽\nЗаработано: {earned} ₽\nВыполнено заданий: {tasks_done}\n\n⚡ Минимум вывода: {min_withdraw} ₽",
            parse_mode="HTML", reply_markup=get_main_keyboard(uid)
        )
    elif text == "📋 Задания":
        if not TASKS:
            update.message.reply_text("📋 <b>Заданий пока нет.</b>\n\nОни скоро появятся. Загляни позже!", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
            return
        update.message.reply_text("📋 <b>Доступные задания</b>\n\nНажми на задание → перейди по ссылке → подпишись → нажми «Проверить»\n\n👑 PRO-подписчики получают x2 награду!", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
    elif text == "🎁 Бонус":
        if can_claim_daily(uid):
            bonus = claim_daily(uid)
            update.message.reply_text(f"🎁 <b>Бонус получен!</b>\n\n+{bonus} ₽ на баланс\n\nЗаходи завтра снова.", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
        else:
            update.message.reply_text("❌ <b>Ты уже получал бонус сегодня</b>\n\nВозвращайся завтра.", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
    elif text == "💸 Вывод":
        balance = row[2] if row else 0
        min_withdraw = get_min_withdraw(uid)
        total_tasks = len(TASKS)
        completed_tasks = get_completed_count(uid)
        if total_tasks > 0 and completed_tasks < total_tasks:
            update.message.reply_text(
                f"❌ <b>ВЫВОД НЕДОСТУПЕН</b>\n\n📋 Выполнено: {completed_tasks} из {total_tasks} заданий\n🚫 Осталось: {total_tasks - completed_tasks}\n\n💰 Баланс: {balance} ₽\n\n✅ Выполни все задания, чтобы получить вывод.",
                parse_mode="HTML", reply_markup=get_main_keyboard(uid)
            )
            return
        if balance < min_withdraw:
            update.message.reply_text(
                f"❌ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n\n💰 Баланс: {balance} ₽\n⚡ Нужно: {min_withdraw} ₽\n\n📋 Выполнено: {completed_tasks} из {total_tasks}\n\n✅ Выполняй задания, чтобы накопить нужную сумму!",
                parse_mode="HTML", reply_markup=get_main_keyboard(uid)
            )
            return
        withdraw_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 СБП (по номеру телефона)", callback_data="withdraw_sbp")],
            [InlineKeyboardButton("💳 Банковская карта", callback_data="withdraw_card")],
            [InlineKeyboardButton("🪙 Криптовалюта (USDT TRC20)", callback_data="withdraw_crypto")],
            [InlineKeyboardButton("⭐ Telegram Stars", callback_data="withdraw_stars")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ])
        update.message.reply_text(
            f"💸 <b>ВЫВОД СРЕДСТВ</b>\n\n💰 Сумма к выводу: <b>{balance} ₽</b>\n\n📝 <b>Выберите способ получения:</b>",
            parse_mode="HTML", reply_markup=withdraw_keyboard
        )
        context.user_data['withdraw_amount'] = balance
    elif text == "📊 Статистика":
        balance = row[2] if row else 0
        earned = row[3] if row else 0
        tasks_done = get_completed_count(uid)
        joined = row[6] if row else "—"
        pro_until = row[7] if row and row[7] else "—"
        total_users, total_earned, total_balance = get_stats()
        update.message.reply_text(
            f"📊 <b>Твоя статистика</b>\n\n💰 Заработано: {earned} ₽\n💳 Доступно: {balance} ₽\n✅ Заданий: {tasks_done}\n📅 В системе с: {joined[:10]}\n👑 PRO до: {pro_until if pro_until != '—' else 'нет'}\n\n📈 <b>Общая статистика</b>\n👤 Пользователей: {total_users}\n💰 Всего заработано: {total_earned} ₽",
            parse_mode="HTML", reply_markup=get_main_keyboard(uid)
        )
    elif text == "❓ Помощь":
        update.message.reply_text(
            "❓ <b>Помощь</b>\n\nПо всем вопросам пиши админу:\n👨‍💻 @n1kolay0_0\n\nОбычно отвечаю в течение нескольких часов.",
            parse_mode="HTML", reply_markup=get_main_keyboard(uid)
        )
    elif text == "💎 PRO Подписка":
        if is_pro:
            update.message.reply_text(f"👑 <b>У тебя уже есть PRO-подписка!</b>\n\nДействует до: {row[7]}\n\nСпасибо за поддержку!", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
        else:
            pro_payment(update, context)
    elif text == "⚡ Админ":
        if uid != ADMIN_ID:
            update.message.reply_text("❌ <b>Нет доступа</b>\n\nЭта панель только для администратора.", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
            return
        update.message.reply_text("✅ <b>АДМИН-ПАНЕЛЬ</b>\n\nДобро пожаловать!", parse_mode="HTML", reply_markup=admin_inline_keyboard())

def handle_withdraw_details(update: Update, context):
    uid = update.effective_user.id
    text = update.message.text.strip()
    if not context.user_data.get('awaiting_withdraw_details'):
        return
    amount = context.user_data.get('withdraw_amount', 0)
    method = context.user_data.get('withdraw_method', 'unknown')
    row = get_user(uid)
    if not row or row[2] < amount:
        update.message.reply_text("❌ Ошибка: баланс изменился. Начни вывод заново.", reply_markup=get_main_keyboard(uid))
        context.user_data['awaiting_withdraw_details'] = False
        return
    method_names = {'sbp': 'СБП (номер телефона)', 'card': 'Банковская карта', 'crypto': 'Криптовалюта USDT TRC20', 'stars': 'Telegram Stars'}
    method_name = method_names.get(method, 'Неизвестный метод')
    # Сохраняем заявку в БД
    save_withdraw_request(uid, update.effective_user.username or update.effective_user.first_name, amount, method_name, text)
    # Списываем сумму
    update_balance(uid, -amount)
    update.message.reply_text(
        f"✅ <b>ЗАЯВКА НА ВЫВОД ОТПРАВЛЕНА!</b>\n\n💰 Сумма: {amount} ₽\n💳 Способ: {method_name}\n📝 Реквизиты: <code>{text}</code>\n\n⏱ Обычно обработка занимает до 24 часов.\n📩 Как только переведу деньги — напишу сюда.\n\n👨‍💻 По вопросам: @n1kolay0_0",
        parse_mode="HTML", reply_markup=get_main_keyboard(uid)
    )
    context.user_data['awaiting_withdraw_details'] = False
    context.user_data['withdraw_amount'] = None
    context.user_data['withdraw_method'] = None

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
            is_pro = check_pro_status(uid)
            pro_text = "\n\n👑 У тебя PRO-подписка! Награды увеличены!" if is_pro else "\n\n💎 Оформи PRO-подписку за 100 Stars и получай увеличенные награды!"
            welcome_text = f"""✨ <b>Привет, {name}!</b> ✨

Это бот для заработка на заданиях.

🔥 <b>Как заработать:</b>
• Выполняй задания (подписки на каналы)
• Забирай ежедневный бонус
• Выводи деньги от {get_min_withdraw(uid)} ₽

🎁 <b>Бонус:</b> +10 ₽ за регистрацию{pro_text}

👇 <b>Нажми на кнопки внизу и зарабатывай!</b>"""
            query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(uid))
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 ПОДПИСАТЬСЯ НА КАНАЛ", url="https://t.me/prof1t_77")],
                [InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
            ])
            query.edit_message_text(
                f"❌ <b>ДОСТУП ЗАПРЕЩЁН</b> ❌\n\nТы ещё не подписан на канал!\n\n👇 <b>Подпишись и нажми «Проверить подписку».</b>",
                parse_mode="HTML", reply_markup=keyboard
            )
        return
    if data.startswith("task_"):
        task_id = int(data.split("_")[1])
        task = next((t for t in TASKS if t["id"] == task_id), None)
        if not task:
            return
        if is_task_completed(uid, task_id):
            query.edit_message_text(f"❌ <b>Задание уже выполнено</b>\n\n{task['name']}\nНаграда: {get_task_reward(uid, task['reward'])} ₽ (уже получена)", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
            return
        reward = get_task_reward(uid, task['reward'])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Перейти к заданию", url=task['url'])],
            [InlineKeyboardButton("✅ Проверить", callback_data=f"check_{task_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_tasks")]
        ])
        query.edit_message_text(f"📌 <b>{task['name']}</b>\n\n💰 Награда: {reward} ₽\n\n📝 Инструкция:\n1. Нажми «Перейти к заданию»\n2. Подпишись на канал/группу\n3. Вернись и нажми «Проверить»\n\n⚡ Бот проверит подписку автоматически.", parse_mode="HTML", reply_markup=keyboard)
        return
    if data.startswith("check_"):
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
        reward = get_task_reward(uid, task['reward'])
        update_balance(uid, reward)
        query.edit_message_text(f"✅ <b>Задание выполнено!</b>\n\n📌 {task['name']}\n💰 Начислено: +{reward} ₽\n\n🎉 Спасибо! Продолжай выполнять задания.", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
        return
    if data == "back_tasks":
        query.edit_message_text("📋 <b>Доступные задания</b>", parse_mode="HTML", reply_markup=tasks_keyboard(uid))
        return
    # Вывод средств
    if data == "withdraw_sbp":
        context.user_data['withdraw_method'] = 'sbp'
        context.user_data['awaiting_withdraw_details'] = True
        query.edit_message_text(f"📱 <b>ВЫВОД НА КАРТУ ЧЕРЕЗ СБП</b>\n\n💰 Сумма: {context.user_data.get('withdraw_amount', 0)} ₽\n\n📝 <b>Введите номер телефона, привязанный к банковской карте:</b>\n\nПример: <code>+79123456789</code>", parse_mode="HTML")
        return
    if data == "withdraw_card":
        context.user_data['withdraw_method'] = 'card'
        context.user_data['awaiting_withdraw_details'] = True
        query.edit_message_text(f"💳 <b>ВЫВОД НА БАНКОВСКУЮ КАРТУ</b>\n\n💰 Сумма: {context.user_data.get('withdraw_amount', 0)} ₽\n\n📝 <b>Введите номер карты (16 цифр) и название банка:</b>\n\nПример: <code>1234 5678 9012 3456, Тинькофф</code>", parse_mode="HTML")
        return
    if data == "withdraw_crypto":
        context.user_data['withdraw_method'] = 'crypto'
        context.user_data['awaiting_withdraw_details'] = True
        query.edit_message_text(f"🪙 <b>ВЫВОД В КРИПТОВАЛЮТЕ (USDT TRC20)</b>\n\n💰 Сумма: {context.user_data.get('withdraw_amount', 0)} ₽\n\n📝 <b>Введите адрес кошелька USDT (сеть TRC20):</b>\n\nПример: <code>TXxx...xxx</code> (42 символа)", parse_mode="HTML")
        return
    if data == "withdraw_stars":
        context.user_data['withdraw_method'] = 'stars'
        context.user_data['awaiting_withdraw_details'] = True
        query.edit_message_text(f"⭐ <b>ВЫВОД TELEGRAM STARS</b>\n\n💰 Сумма: {context.user_data.get('withdraw_amount', 0)} ₽\n\n📝 <b>Введите ваш username в Telegram:</b>\n\nПример: <code>@username</code>\n\n⚠️ Stars будут отправлены через @PremiumBot", parse_mode="HTML")
        return
    if data == "back_to_menu":
        query.edit_message_text("🤝 <b>Главное меню</b>", parse_mode="HTML", reply_markup=get_main_keyboard(uid))
        return
    # Админ-панель
    if uid != ADMIN_ID:
        query.edit_message_text("❌ Нет доступа")
        return
    if data == "admin_give":
        query.edit_message_text("💰 <b>Выдать деньги</b>\n\n/give ID сумма\n\nПример: /give 6127276408 100", parse_mode="HTML")
    elif data == "admin_broadcast":
        query.edit_message_text("📢 <b>Рассылка</b>\n\n/broadcast текст\n\nПример: /broadcast Всем привет!", parse_mode="HTML")
    elif data == "admin_users":
        users = get_all_users()
        if not users:
            query.edit_message_text("Нет пользователей")
            return
        text = "👥 <b>Список пользователей</b>\n\n"
        for u in users[:20]:
            pro = " 👑" if u[4] and datetime.now() < datetime.strptime(u[4], '%Y-%m-%d') else ""
            text += f"@{u[1] or u[0]}{pro} | {u[2]} ₽\n"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_stats":
        total_users, total_earned, total_balance = get_stats()
        text = f"📊 <b>Статистика</b>\n\n👥 Пользователей: {total_users}\n💰 Заработано: {total_earned} ₽\n💳 На балансе: {total_balance} ₽"
        query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_bonus_all":
        query.edit_message_text("🎁 <b>Бонус всем</b>\n\n/bonus_all сумма\n\nПример: /bonus_all 10", parse_mode="HTML")
    elif data == "admin_add_task":
        query.edit_message_text("📝 <b>Добавить задание</b>\n\n/add_task название | @username | награда\n\nПример:\n/add_task Подпишись на канал | @example | 10", parse_mode="HTML")
    elif data == "admin_pro_on":
        query.edit_message_text("👑 <b>Включить PRO-подписку</b>\n\n/pro_on ID\n\nПример: /pro_on 6127276408", parse_mode="HTML")
    elif data == "admin_pro_off":
        query.edit_message_text("👑 <b>Выключить PRO-подписку</b>\n\n/pro_off ID\n\nПример: /pro_off 6127276408", parse_mode="HTML")
    elif data == "admin_withdraw_requests":
        requests = get_pending_requests()
        if not requests:
            query.edit_message_text("💳 <b>Нет новых заявок на вывод</b>", parse_mode="HTML", reply_markup=admin_inline_keyboard())
            return
        text = "💳 <b>ЗАЯВКИ НА ВЫВОД</b>\n\n"
        for req in requests:
            text += f"🆔 {req[0]} | @{req[2] or req[1]} | {req[3]} ₽ | {req[4]}\n📝 {req[5]}\n📅 {req[6]}\n➖➖➖➖➖➖➖\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Отметить как выплачено", callback_data="admin_mark_paid")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_back_to_menu")]
        ])
        query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    elif data == "admin_mark_paid":
        query.edit_message_text(
            "✅ <b>Отметить заявку как выплаченную</b>\n\nВведи номер заявки:\n<code>/pay ID_заявки</code>\n\nПример: <code>/pay 1</code>",
            parse_mode="HTML", reply_markup=admin_inline_keyboard()
        )
    elif data == "admin_back_to_menu":
        query.edit_message_text("✅ <b>АДМИН-ПАНЕЛЬ</b>\n\nДобро пожаловать!", parse_mode="HTML", reply_markup=admin_inline_keyboard())
    elif data == "admin_close":
        query.edit_message_text("🔒 Админ-панель закрыта", reply_markup=get_main_keyboard(uid))

def pay_request_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        request_id = int(context.args[0])
        complete_request(request_id)
        update.message.reply_text(f"✅ Заявка #{request_id} отмечена как выплаченная")
    except:
        update.message.reply_text("❌ Используй: /pay ID_заявки")

def pro_on_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        if check_pro_status(user_id):
            update.message.reply_text(f"👑 У пользователя {user_id} уже есть PRO-подписка")
            return
        activate_pro(user_id, 30)
        update.message.reply_text(f"✅ PRO-подписка включена пользователю {user_id} на 30 дней")
        try:
            context.bot.send_message(user_id, "🎉 Администратор включил тебе PRO-подписку на 30 дней! 👑\n\nНаграды увеличены в 2 раза!")
        except:
            pass
    except:
        update.message.reply_text("❌ Используй: /pro_on ID")

def pro_off_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        if not check_pro_status(user_id):
            update.message.reply_text(f"👑 У пользователя {user_id} нет PRO-подписки")
            return
        deactivate_pro(user_id)
        update.message.reply_text(f"✅ PRO-подписка выключена пользователю {user_id}")
        try:
            context.bot.send_message(user_id, "⚠️ Администратор отключил PRO-подписку.")
        except:
            pass
    except:
        update.message.reply_text("❌ Используй: /pro_off ID")

def pro_status_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        is_pro = check_pro_status(user_id)
        row = get_user(user_id)
        if is_pro:
            update.message.reply_text(f"👑 Пользователь {user_id} имеет PRO-подписку до {row[7]}")
        else:
            update.message.reply_text(f"👑 Пользователь {user_id} не имеет PRO-подписку")
    except:
        update.message.reply_text("❌ Используй: /pro_status ID")

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
        update.message.reply_text(f"✅ Задание добавлено!\n\n{name}\n{url}\n💰 {reward} ₽ (для PRO x2)")
    except:
        update.message.reply_text("❌ Ошибка. Используй: /add_task название | @username | награда")

def id_command(update: Update, context):
    uid = update.effective_user.id
    is_pro = check_pro_status(uid)
    pro_text = " (PRO 👑)" if is_pro else ""
    update.message.reply_text(f"🆔 Твой ID: {uid}{pro_text}")

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
    dp.add_handler(CommandHandler("pro_on", pro_on_command))
    dp.add_handler(CommandHandler("pro_off", pro_off_command))
    dp.add_handler(CommandHandler("pro_status", pro_status_command))
    dp.add_handler(CommandHandler("pay", pay_request_command))
    dp.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_buttons))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_withdraw_details))
    dp.add_handler(PreCheckoutQueryHandler(pre_checkout))
    dp.add_handler(MessageHandler(Filters.successful_payment, successful_payment))
    updater.start_polling()
    print("Бот запущен!")
    updater.idle()
