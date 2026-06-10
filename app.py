import os
from threading import Thread
from flask import Flask
from bot import bot, dp
from aiogram.utils import executor

app = Flask(__name__)

@app.route('/')
def index():
    return "Реферальный бот работает!"

@app.route('/health')
def health():
    return "OK"

def run_bot():
    executor.start_polling(dp, skip_updates=True)

if __name__ == "__main__":
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
