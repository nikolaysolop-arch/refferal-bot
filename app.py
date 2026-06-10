import os
from threading import Thread
from flask import Flask
from bot import app as telegram_app

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Referral bot is running!"

@flask_app.route('/health')
def health():
    return "OK"

def run_bot():
    telegram_app.run_polling()

if __name__ == "__main__":
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)
