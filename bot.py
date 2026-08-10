import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======== ПРОКСИ ========
PROXY_URL = os.environ.get('PROXY_URL', '')
if PROXY_URL:
    os.environ['HTTP_PROXY'] = PROXY_URL
    os.environ['HTTPS_PROXY'] = PROXY_URL
    print(f"🔑 Прокси: {PROXY_URL}")
else:
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''
    print("ℹ️ Без прокси")

import telebot
import secrets
import requests
from datetime import datetime, timedelta
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

# ======== ДАННЫЕ ИЗ ПЕРЕМЕННЫХ ========
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8986978297:AAFTH0pRKjbHBbmGLIAv5xUsShld4cuw_0Y')
FIREBASE_URL = os.environ.get('FIREBASE_DATABASE_URL', 'https://cookiebuystore-default-rtdb.firebaseio.com/')
SITE_URL = os.environ.get('SITE_URL', 'https://cookieusergg-a11y.github.io/CookieBuy/')
ADMIN_IDS = [int(id.strip()) for id in os.environ.get('ADMIN_IDS', '8835124014').split(',')]

CRYPTO_WALLET = os.environ.get('CRYPTO_WALLET', 'UQAwY-Xnk6y0l2f_3h51zX--G1hflpS3ZvI8MRshYcfHskWA')
CRYPTO_NETWORK = os.environ.get('CRYPTO_NETWORK', 'TON (USDT)')

# ======== СОЗДАЁМ БОТА ========
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
session.proxies = {}
session.trust_env = False
bot.session = session

# ======== FLASK ========
app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "🤖 CookieBuy Bot is running!"

@app.route('/api/wallet', methods=['GET'])
def get_wallet():
    return jsonify({
        "address": CRYPTO_WALLET,
        "network": CRYPTO_NETWORK
    })

# ======== КОМАНДЫ БОТА ========
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        f"🤖 **CookieBuy Бот работает!**\n\n"
        f"💳 Кошелёк: `{CRYPTO_WALLET}`\n"
        f"🌐 Сеть: {CRYPTO_NETWORK}"
    )

# ======== ЗАПУСК ========
def run_bot():
    try:
        print("🤖 Бот запускается...")
        bot.polling(none_stop=True, timeout=30)
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("=" * 50)
    print("🤖 COOKIEBUY БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"💳 Кошелёк: {CRYPTO_WALLET}")
    print(f"📱 Сайт: {SITE_URL}")
    print("=" * 50)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
