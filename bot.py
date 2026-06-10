import sqlite3
import random
import string
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

# ==================== КОНФИГ ====================
BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

# Настройки заработка
REFERRAL_REWARD = 15.0      # Бонус пригласившему за друга
REFERRED_REWARD = 10.0      # Бонус новому пользователю
DAILY_BONUS = 5.0           # Ежедневный бонус
MIN_WITHDRAW = 100.0        # Минималка вывода

# Партнёрские ссылки (куда ведём пользователей)
PARTNER_LINKS = {
    "ozon": "https://ozon.ru/?partner=YOUR_ID",
    "wildberries": "https://wildberries.ru/?partner=YOUR_ID",
    "aliexpress": "https://aliexpress.ru/?partner=YOUR_ID",
    "kwork": "https://kwork.ru/?ref=YOUR_ID",
    "profittrade": "https://t.me/profittrade?start=YOUR_ID"
}

# Промокоды
PROMO_CODES = {
    "START2025": 50.0,
    "BONUS100": 100.0,
    "FRIEND2025": 75.0
}

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
                  clicks_count INTEGER DEFAULT 0,
                  last_daily DATE,
                  last_activity DATE,
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
                'referrals_count': row[6], 'clicks_count': row[7],
                'last_daily': row[8], 'last_activity': row[9], 'joined_date': row[10]}
    return None

def create_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    try:
        c.execute("""INSERT INTO users 
                     (user_id, username, referrer_id, referral_code, last_activity, joined_date) 
                     VALUES (?,?,?,?,?,?)""",
                  (user_id, username, referrer_id, code, 
                   datetime.now().strftime('%Y-%m-%d'), 
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
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
    return True

def add_referral(referrer_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()

def add_click(user_id):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET clicks_count = clicks_count + 1, last_activity = ? WHERE user_id = ?", 
              (datetime.now().strftime('%Y-%m-%d'), user_id))
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
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", 
              (datetime.now().strftime('%Y-%m-%d'), user_id))
    conn.commit()
    conn.close()
    update_balance(user_id, DAILY_BONUS)
    return DAILY_BONUS

def get_top_referrals(limit=10):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_top_earners(limit=10):
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT username, total_earned FROM users WHERE total_earned > 0 ORDER BY total_earned DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def apply_promo(user_id, code):
    if code in PROMO_CODES:
        amount = PROMO_CODES[code]
        update_balance(user_id, amount)
        return True, amount
    return False, 0

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard(user_id):
    u = get_user(user_id)
    bal = u['balance'] if u else 0
    keyboard = [
        [InlineKeyboardButton(f"💰 БАЛАНС: {bal:.2f} ₽", callback_data='balance')],
        [InlineKeyboardButton("👥 РЕФЕРАЛЫ", callback_data='referrals'), 
         InlineKeyboardButton("🔗 МОЯ ССЫЛКА", callback_data='link')],
        [InlineKeyboardButton("🏆 ТОП РЕФЕРАЛОВ", callback_data='top_refs'),
         InlineKeyboardButton("⭐ ТОП ЗАРАБОТКА", callback_data='top_earners')],
        [InlineKeyboardButton("🎁 ЕЖЕДНЕВНЫЙ БОНУС", callback_data='daily')],
        [InlineKeyboardButton("🎟 ПРОМОКОД", callback_data='promo')],
        [InlineKeyboardButton("💸 ВЫВЕСТИ ДЕНЬГИ", callback_data='withdraw')],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data='stats')],
        [InlineKeyboardButton("💰 ЗАРАБОТАТЬ", callback_data='earn')],
        [InlineKeyboardButton("❓ ПОДДЕРЖКА", callback_data='support')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_earn_keyboard():
    keyboard = [
        [InlineKeyboardButton("🛍 Ozon", url=PARTNER_LINKS['ozon']),
         InlineKeyboardButton("👕 Wildberries", url=PARTNER_LINKS['wildberries'])],
        [InlineKeyboardButton("📦 AliExpress", url=PARTNER_LINKS['aliexpress']),
         InlineKeyboardButton("💼 Kwork", url=PARTNER_LINKS['kwork'])],
        [InlineKeyboardButton("📈 Profittrade", url=PARTNER_LINKS['profittrade'])],
        [InlineKeyboardButton("🔙 НАЗАД", callback_data='menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ОБРАБОТЧИКИ ====================
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Referral Bot is running!"

@flask_app.route('/health')
def health():
    return jsonify({"status": "ok"})

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

def start(update: Update, context):
    uid = update.effective_user.id
    name = update.effective_user.username or update.effective_user.first_name
    ref_id = None
    
    # Обработка реферального кода
    if context.args:
        code = context.args[0]
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,))
        r = c.fetchone()
        conn.close()
        if r and r[0] != uid:
            ref_id = r[0]
    
    # Регистрация
    if not get_user(uid):
        create_user(uid, name, ref_id)
        if ref_id:
            update_balance(ref_id, REFERRAL_REWARD)
            add_referral(ref_id)
            update_balance(uid, REFERRED_REWARD)
            context.bot.send_message(ref_id, f"🎉 НОВЫЙ РЕФЕРАЛ!\n@{name} присоединился по твоей ссылке!\n💰 Начислено: +{REFERRAL_REWARD} ₽")
            context.bot.send_message(ADMIN_ID, f"📢 Новый пользователь: @{name}\nПриглашён: @{get_user(ref_id)['username']}")
            update.message.reply_text(f"🎉 БОНУС {REFERRED_REWARD} ₽ ЗА РЕГИСТРАЦИЮ!")
    
    # Приветствие
    welcome_text = (
        "🤖 <b>ДОБРО ПОЖАЛОВАТЬ В РЕФЕРАЛЬНОГО БОТА!</b>\n\n"
        "🔥 <b>КАК ЗАРАБОТАТЬ:</b>\n"
        "• Приглашай друзей — получай 15 ₽ за каждого\n"
        "• Ежедневный бонус — 5 ₽ каждый день\n"
        "• Используй промокоды — до 100 ₽ бонусом\n"
        "• Переходи по партнёрским ссылкам — зарабатывай на покупках\n\n"
        f"💎 ТВОЯ РЕФЕРАЛЬНАЯ ССЫЛКА:\n"
        f"<code>https://t.me/{context.bot.username}?start={get_user(uid)['referral_code']}</code>\n\n"
        "👇 ВЫБЕРИ ДЕЙСТВИЕ:"
    )
    update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=get_main_keyboard(uid))

def button_handler(update: Update, context):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = query.from_user.id
    u = get_user(uid)
    
    if data == 'balance':
        query.edit_message_text(
            f"💰 <b>ТВОЙ БАЛАНС</b>\n\n"
            f"💵 Доступно: {u['balance']:.2f} ₽\n"
            f"📈 Всего заработано: {u['total_earned']:.2f} ₽\n"
            f"👥 Приглашено друзей: {u['referrals_count']}\n"
            f"🖱 Переходов по ссылкам: {u['clicks_count']}\n\n"
            f"⚡ Минимум для вывода: {MIN_WITHDRAW} ₽",
            parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'link':
        url = f"https://t.me/{context.bot.username}?start={u['referral_code']}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={url}&text=Зарабатывай со мной!")],
            [InlineKeyboardButton("🔙 НАЗАД", callback_data='menu')]
        ])
        query.edit_message_text(
            f"🔗 <b>ТВОЯ РЕФЕРАЛЬНАЯ ССЫЛКА</b>\n\n"
            f"<code>{url}</code>\n\n"
            f"📢 За каждого друга по ссылке ты получаешь +{REFERRAL_REWARD} ₽!\n"
            f"🎁 Друг тоже получает бонус {REFERRED_REWARD} ₽ при регистрации.",
            parse_mode='HTML', reply_markup=keyboard)
    
    elif data == 'referrals':
        if u['referrals_count'] == 0:
            query.edit_message_text("👥 У тебя пока нет рефералов.\nПригласи друзей по своей ссылке!", reply_markup=get_main_keyboard(uid))
            return
        conn = sqlite3.connect('referral_bot.db')
        c = conn.cursor()
        c.execute("SELECT username, joined_date FROM users WHERE referrer_id = ? ORDER BY joined_date DESC LIMIT 20", (uid,))
        rows = c.fetchall()
        conn.close()
        txt = f"👥 <b>ТВОИ РЕФЕРАЛЫ ({u['referrals_count']})</b>\n\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. @{r[0] or 'скрыто'} — {r[1][:10]}\n"
        query.edit_message_text(txt, parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'top_refs':
        top = get_top_referrals()
        if not top:
            query.edit_message_text("🏆 Пока нет рефералов в топе. Будь первым!", reply_markup=get_main_keyboard(uid))
            return
        txt = "🏆 <b>ТОП РЕФЕРАЛОВ</b>\n\n"
        for i, (username, count) in enumerate(top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
            txt += f"{medal} {i}. @{username or 'anon'} — {count} рефералов\n"
        query.edit_message_text(txt, parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'top_earners':
        top = get_top_earners()
        if not top:
            query.edit_message_text("⭐ Пока нет заработавших. Будь первым!", reply_markup=get_main_keyboard(uid))
            return
        txt = "⭐ <b>ТОП ЗАРАБОТКА</b>\n\n"
        for i, (username, earned) in enumerate(top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💰"
            txt += f"{medal} {i}. @{username or 'anon'} — {earned:.2f} ₽\n"
        query.edit_message_text(txt, parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'daily':
        if can_claim_daily(uid):
            amount = claim_daily(uid)
            query.edit_message_text(f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\n\n💰 Ты получил +{amount} ₽\n📅 Завтра сможешь забрать снова!", parse_mode='HTML', reply_markup=get_main_keyboard(uid))
        else:
            query.edit_message_text("❌ Ты уже получал бонус сегодня!\n📅 Заходи завтра снова.", reply_markup=get_main_keyboard(uid))
    
    elif data == 'promo':
        query.edit_message_text("🎟 <b>ВВЕДИ ПРОМОКОД</b>\n\nДоступные промокоды:\n• START2025 — 50 ₽\n• BONUS100 — 100 ₽\n• FRIEND2025 — 75 ₽\n\nВведите код в чат:", parse_mode='HTML', reply_markup=main_keyboard(uid))
        context.user_data['awaiting_promo'] = True
    
    elif data == 'stats':
        query.edit_message_text(
            f"📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
            f"👥 Рефералов: {u['referrals_count']}\n"
            f"💰 Всего заработано: {u['total_earned']:.2f} ₽\n"
            f"💳 Доступно для вывода: {u['balance']:.2f} ₽\n"
            f"🖱 Переходов по ссылкам: {u['clicks_count']}\n"
            f"📅 В системе с: {u['joined_date'][:10]}\n"
            f"📆 Последняя активность: {u['last_activity']}",
            parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'withdraw':
        if u['balance'] < MIN_WITHDRAW:
            query.answer(f"❌ Минимальная сумма вывода: {MIN_WITHDRAW} ₽\nТвой баланс: {u['balance']:.2f} ₽", show_alert=True)
            return
        context.bot.send_message(ADMIN_ID, 
            f"💳 <b>ЗАЯВКА НА ВЫВОД</b>\n\n"
            f"👤 Пользователь: @{query.from_user.username}\n"
            f"🆔 ID: {uid}\n"
            f"💰 Сумма: {u['balance']:.2f} ₽\n"
            f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode='HTML')
        query.edit_message_text(
            f"✅ <b>ЗАЯВКА НА ВЫВОД ОТПРАВЛЕНА!</b>\n\n"
            f"💰 Сумма: {u['balance']:.2f} ₽\n\n"
            f"📝 Администратор свяжется с тобой в ближайшее время.\n"
            f"⏱ Обычно обработка занимает до 24 часов.",
            parse_mode='HTML', reply_markup=get_main_keyboard(uid))
    
    elif data == 'earn':
        query.edit_message_text(
            "💰 <b>ДОПОЛНИТЕЛЬНЫЙ ЗАРАБОТОК</b>\n\n"
            "🔥 Переходи по ссылкам ниже и зарабатывай:\n"
            "• Кэшбэк до 30% на покупках\n"
            "• Бонусы за регистрацию\n"
            "• Партнёрские программы\n\n"
            "<i>Каждый переход по ссылке увеличивает твой рейтинг!</i>",
            parse_mode='HTML', reply_markup=get_earn_keyboard())
    
    elif data == 'support':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 НАПИСАТЬ АДМИНУ", url=f"https://t.me/mskvoru")],
            [InlineKeyboardButton("🔙 НАЗАД", callback_data='menu')]
        ])
        query.edit_message_text(
            "❓ <b>ПОДДЕРЖКА</b>\n\n"
            "По всем вопросам:\n"
            "• Вывод средств\n"
            "• Проблемы с ботом\n"
            "• Сотрудничество\n\n"
            "Нажми на кнопку ниже, чтобы связаться с администратором.",
            parse_mode='HTML', reply_markup=keyboard)
    
    elif data == 'menu':
        query.edit_message_text("🤝 <b>ГЛАВНОЕ МЕНЮ</b>", parse_mode='HTML', reply_markup=get_main_keyboard(uid))

def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_promo'):
        code = text.strip().upper()
        success, amount = apply_promo(user_id, code)
        if success:
            update.message.reply_text(f"✅ <b>ПРОМОКОД АКТИВИРОВАН!</b>\n\n💰 Ты получил +{amount} ₽ бонуса.\n📊 Проверь баланс в главном меню.", parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
        else:
            update.message.reply_text(f"❌ <b>НЕВЕРНЫЙ ПРОМОКОД</b>\n\nКод '{code}' не найден.\nПопробуй один из: START2025, BONUS100, FRIEND2025", parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
        context.user_data['awaiting_promo'] = False
    else:
        # Считаем переход по партнёрской ссылке, если пользователь отправил её
        add_click(user_id)
        update.message.reply_text("🤖 Используй кнопки меню для навигации:", reply_markup=get_main_keyboard(user_id))

# ==================== АДМИН-КОМАНДЫ ====================
def admin_stats(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    c.execute("SELECT SUM(total_earned) FROM users")
    total_earned = c.fetchone()[0] or 0
    c.execute("SELECT SUM(referrals_count) FROM users")
    total_refs = c.fetchone()[0] or 0
    c.execute("SELECT SUM(clicks_count) FROM users")
    total_clicks = c.fetchone()[0] or 0
    conn.close()
    update.message.reply_text(
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👥 Всего рефералов: {total_refs}\n"
        f"💰 Всего заработано: {total_earned:.2f} ₽\n"
        f"💳 На балансе: {total_balance:.2f} ₽\n"
        f"🖱 Переходов: {total_clicks}",
        parse_mode='HTML')

def admin_broadcast(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    if not context.args:
        update.message.reply_text("❌ Используй: /broadcast текст")
        return
    text = ' '.join(context.args)
    conn = sqlite3.connect('referral_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    success = 0
    for user in users:
        try:
            context.bot.send_message(user[0], f"📢 <b>РАССЫЛКА</b>\n\n{text}", parse_mode='HTML')
            success += 1
        except:
            pass
    update.message.reply_text(f"✅ Рассылка отправлена {success} пользователям")

def admin_bonus(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        update_balance(user_id, amount)
        context.bot.send_message(user_id, f"🎁 <b>АДМИН НАЧИСЛИЛ БОНУС!</b>\n\n💰 +{amount} ₽ на баланс.", parse_mode='HTML')
        update.message.reply_text(f"✅ Начислено {amount} ₽ пользователю {user_id}")
    except:
        update.message.reply_text("❌ Используй: /bonus user_id сумма")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    init_db()
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    
    # Пользовательские команды
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text, handle_message))
    
    # Админ-команды
    dp.add_handler(CommandHandler("admin", admin_stats))
    dp.add_handler(CommandHandler("broadcast", admin_broadcast))
    dp.add_handler(CommandHandler("bonus", admin_bonus))
    
    updater.start_polling()
    print("🤖 Бот запущен!")
    updater.idle()
