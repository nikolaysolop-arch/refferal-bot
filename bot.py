from telegram import Update
from telegram.ext import Updater, CommandHandler
from flask import Flask
from threading import Thread

BOT_TOKEN = "8309241267:AAHoQhI7TXoDIbTeb1wiSQ9zjc6UwddgnG0"
ADMIN_ID = 6127276408

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

def start(update: Update, context):
    update.message.reply_text("✅ Бот работает!\n\nДоступные команды:\n/start - Проверить бота\n/id - Узнать свой ID\n/give - Выдать деньги (админ)\n/take - Забрать деньги (админ)")

def id_command(update: Update, context):
    user_id = update.effective_user.id
    update.message.reply_text(f"🆔 Твой ID: {user_id}")

def give_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа. Ты не админ.")
        return
    
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        update.message.reply_text(f"✅ Выдано {amount} ₽ пользователю {user_id}")
    except:
        update.message.reply_text("❌ Используй: /give ID сумма\nПример: /give 6127276408 100")

def take_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Нет доступа. Ты не админ.")
        return
    
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        update.message.reply_text(f"✅ Забрано {amount} ₽ у пользователя {user_id}")
    except:
        update.message.reply_text("❌ Используй: /take ID сумма\nПример: /take 6127276408 50")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    
    updater = Updater(token=BOT_TOKEN)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("id", id_command))
    dp.add_handler(CommandHandler("give", give_command))
    dp.add_handler(CommandHandler("take", take_command))
    
    updater.start_polling()
    print("Бот запущен!")
    updater.idle()
