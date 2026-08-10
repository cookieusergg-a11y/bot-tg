import os
import telebot
import secrets
import json
import requests
from datetime import datetime, timedelta
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

# ======== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ========
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8986978297:AAFTH0pRKjbHBbmGLIAv5xUsShld4cuw_0Y')
FIREBASE_URL = os.environ.get('FIREBASE_DATABASE_URL', 'https://cookiebuystore-default-rtdb.firebaseio.com/')
SITE_URL = os.environ.get('SITE_URL', 'https://cookieusergg-a11y.github.io/CookieBuy/')
ADMIN_IDS = [int(id.strip()) for id in os.environ.get('ADMIN_IDS', '8835124014').split(',')]

CRYPTO_WALLET = os.environ.get('CRYPTO_WALLET', 'UQAwY-Xnk6y0l2f_3h51zX--G1hflpS3ZvI8MRshYcfHskWA')
CRYPTO_NETWORK = os.environ.get('CRYPTO_NETWORK', 'TON (USDT)')

CODE_LENGTH = int(os.environ.get('CODE_LENGTH', 5))
CODE_EXPIRY_MINUTES = int(os.environ.get('CODE_EXPIRY_MINUTES', 5))
LINK_EXPIRY_MINUTES = int(os.environ.get('LINK_EXPIRY_MINUTES', 10))

# ======== ОТКЛЮЧАЕМ ПРОКСИ ========
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['NO_PROXY'] = '*'

# ======== СОЗДАЁМ БОТА ========
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
session.proxies = {}
session.trust_env = False
bot.session = session

# Хранилища
temp_links = {}
pending_codes = {}

# ======== FIREBASE ФУНКЦИИ ========
def save_tg_link(uid, link, expires_at, tg_id):
    data = {
        "tg_id": tg_id,
        "link": link,
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.now().isoformat()
    }
    url = f"{FIREBASE_URL}telegram_links/{uid}.json"
    response = requests.put(url, json=data, proxies={})
    return response.status_code == 200

def get_tg_link(uid):
    url = f"{FIREBASE_URL}telegram_links/{uid}.json"
    response = requests.get(url, proxies={})
    if response.status_code == 200:
        return response.json()
    return None

def mark_link_used(uid):
    url = f"{FIREBASE_URL}telegram_links/{uid}/used.json"
    response = requests.put(url, json=True, proxies={})
    return response.status_code == 200

def save_tg_user(firebase_uid, tg_user):
    data = {
        "tg_id": tg_user.id,
        "tg_username": tg_user.username or "",
        "tg_first_name": tg_user.first_name or "",
        "tg_last_name": tg_user.last_name or "",
        "linked_at": datetime.now().isoformat()
    }
    url = f"{FIREBASE_URL}users/{firebase_uid}/telegram.json"
    response = requests.put(url, json=data, proxies={})
    return response.status_code == 200

def get_user_by_tg(tg_id):
    url = f"{FIREBASE_URL}users.json?orderBy=\"telegram/tg_id\"&equalTo={tg_id}"
    response = requests.get(url, proxies={})
    if response.status_code == 200 and response.json():
        items = list(response.json().items())
        if items:
            return items[0][0], items[0][1]
    return None, None

def get_inventory(firebase_uid):
    url = f"{FIREBASE_URL}users/{firebase_uid}/inventory.json"
    response = requests.get(url, proxies={})
    if response.status_code == 200:
        data = response.json()
        if data:
            return [(key, value) for key, value in data.items()]
    return []

def save_promocode(code, data):
    url = f"{FIREBASE_URL}promocodes/{code}.json"
    response = requests.put(url, json=data, proxies={})
    return response.status_code == 200

def get_promocode(code):
    url = f"{FIREBASE_URL}promocodes/{code}.json"
    response = requests.get(url, proxies={})
    if response.status_code == 200:
        return response.json()
    return None

def use_promocode(code, user_id):
    url = f"{FIREBASE_URL}promocodes/{code}/used_by/{user_id}.json"
    response = requests.put(url, json=datetime.now().isoformat(), proxies={})
    return response.status_code == 200

def generate_tg_code():
    """Генерирует код указанной длины (по умолчанию 5 цифр)"""
    return ''.join(secrets.choice('0123456789') for _ in range(CODE_LENGTH))

def create_firebase_user(tg_id, tg_username, tg_first_name, tg_last_name):
    firebase_uid = f"tg_{tg_id}_{int(time.time())}"
    user_data = {
        "telegram": {
            "tg_id": tg_id,
            "tg_username": tg_username or "",
            "tg_first_name": tg_first_name or "Telegram",
            "tg_last_name": tg_last_name or "",
            "linked_at": datetime.now().isoformat()
        },
        "created_at": datetime.now().isoformat()
    }
    url = f"{FIREBASE_URL}users/{firebase_uid}.json"
    response = requests.put(url, json=user_data, proxies={})
    if response.status_code == 200:
        return firebase_uid
    return None

# ======== КОМАНДЫ БОТА ========
@bot.message_handler(commands=['start'])
def start(message):
    text = message.text
    if ' ' in text:
        payload = text.split(' ', 1)[1]
        if payload.startswith('tg_'):
            handle_tg_login(message, payload)
            return
    
    bot.reply_to(
        message,
        f"🤖 **CookieBuy Бот**\n\n"
        "Доступные команды:\n"
        "/link - получить ссылку для привязки\n"
        "/status - статус привязки\n"
        "/inventory - инвентарь\n"
        "/getcode - получить код TG аккаунта\n"
        "/wallet - кошелёк для оплаты\n\n"
        f"💳 Кошелёк: `{CRYPTO_WALLET}`\nСеть: {CRYPTO_NETWORK}"
    )

def handle_tg_login(message, payload):
    tg_id = message.from_user.id
    tg_username = message.from_user.username or ""
    tg_first_name = message.from_user.first_name or "Telegram"
    tg_last_name = message.from_user.last_name or ""
    
    firebase_uid = create_firebase_user(tg_id, tg_username, tg_first_name, tg_last_name)
    
    if firebase_uid:
        db_url = f"{FIREBASE_URL}telegram_pending/{payload}.json"
        data = {
            "status": "confirmed",
            "firebase_uid": firebase_uid,
            "tg_id": tg_id,
            "tg_username": tg_username,
            "tg_first_name": tg_first_name,
            "tg_last_name": tg_last_name,
            "confirmed_at": datetime.now().isoformat()
        }
        requests.put(db_url, json=data, proxies={})
        
        bot.reply_to(
            message,
            "✅ **Вы зарегистрировались на сайте CookieBuy!**\n\n"
            f"👤 Ник: {tg_first_name}\n"
            f"🆔 Username: @{tg_username if tg_username else 'не указан'}\n\n"
            "Вернитесь на сайт и нажмите **'Проверить вход'**"
        )
    else:
        bot.reply_to(message, "❌ Ошибка регистрации")

@bot.message_handler(commands=['link'])
def send_link(message):
    uid = secrets.token_hex(8)
    expires_at = (datetime.now() + timedelta(minutes=LINK_EXPIRY_MINUTES)).isoformat()
    link = f"{SITE_URL}?tg_link={uid}"
    
    if save_tg_link(uid, link, expires_at, message.from_user.id):
        temp_links[uid] = {
            "tg_id": message.from_user.id,
            "expires_at": expires_at
        }
        bot.reply_to(
            message,
            f"🔗 **Ваша ссылка для привязки:**\n\n{link}\n\n⏳ Действует {LINK_EXPIRY_MINUTES} минут"
        )
    else:
        bot.reply_to(message, "❌ Ошибка")

@bot.message_handler(commands=['status'])
def check_status(message):
    uid, data = get_user_by_tg(message.from_user.id)
    if uid:
        bot.reply_to(
            message,
            "✅ **Аккаунт привязан!**\n"
            f"🆔 ID: `{uid[:8]}...`"
        )
    else:
        bot.reply_to(message, "❌ Аккаунт не привязан. Используйте /link")

@bot.message_handler(commands=['inventory'])
def show_inventory(message):
    uid, data = get_user_by_tg(message.from_user.id)
    if not uid:
        bot.reply_to(message, "❌ Привяжите аккаунт через /link")
        return
    
    inventory = get_inventory(uid)
    if not inventory:
        bot.reply_to(message, "📭 Инвентарь пуст")
        return
    
    text = "📦 **Ваш инвентарь:**\n\n"
    for item_id, item in inventory[:10]:
        status_icon = "✅" if item.get('status') == 'active' else "❌"
        if item.get('status') == 'waiting_code':
            status_icon = "⏳"
        text += f"{status_icon} **{item.get('type', 'unknown').upper()}**\n"
        text += f"   💰 {item.get('price', 0)} USDT\n"
        text += f"   🆔 `{item_id[:8]}...`\n\n"
    
    if len(inventory) > 10:
        text += f"... и ещё {len(inventory) - 10} товаров"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['getcode'])
def get_telegram_code(message):
    uid, data = get_user_by_tg(message.from_user.id)
    if not uid:
        bot.reply_to(message, "❌ Привяжите аккаунт через /link")
        return
    
    inventory = get_inventory(uid)
    waiting = []
    for item_id, item in inventory:
        if item.get('type') == 'tg' and item.get('status') == 'waiting_code':
            waiting.append((item_id, item))
    
    if not waiting:
        bot.reply_to(message, "📭 Нет аккаунтов, ожидающих код")
        return
    
    item_id, item = waiting[0]
    phone = item.get('data', 'неизвестно')
    twofa = item.get('twofa', '')
    
    code = generate_tg_code()
    pending_codes[item_id] = {
        'tg_id': message.from_user.id,
        'code': code,
        'expires': datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
    }
    
    db_url = f"{FIREBASE_URL}users/{uid}/inventory/{item_id}/code.json"
    requests.put(db_url, json=code, proxies={})
    
    bot.reply_to(
        message,
        f"📱 **Telegram аккаунт**\n\n"
        f"Номер: `{phone}`\n"
        f"Код: `{code}`\n"
        f"2FA: {'есть' if twofa else 'нет'}\n\n"
        f"⏳ Код действителен {CODE_EXPIRY_MINUTES} минут\n"
        f"⚠️ Код привязан к номеру {phone}"
    )

@bot.message_handler(commands=['wallet'])
def show_wallet(message):
    bot.reply_to(
        message,
        f"💳 **Кошелёк для оплаты**\n\n"
        f"Адрес: `{CRYPTO_WALLET}`\n"
        f"Сеть: {CRYPTO_NETWORK}"
    )

# ======== АДМИН-КОМАНДЫ ========
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ Доступ запрещён")
        return
    
    bot.reply_to(
        message,
        "⚙️ **Админ-панель**\n\n"
        "/add_promo [code] [discount] [type] - добавить промокод\n"
        "/stats - статистика\n"
        "/add_cookie [data] [price] - добавить куку\n"
        "/add_tg [phone] [price] - добавить TG аккаунт"
    )

@bot.message_handler(commands=['add_promo'])
def add_promo(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        bot.reply_to(message, "❌ /add_promo [code] [discount] [type]")
        return
    
    code = parts[1].upper()
    discount = float(parts[2])
    promo_type = parts[3]
    expires = (datetime.now() + timedelta(days=30)).isoformat()
    
    data = {
        "discount": discount,
        "type": promo_type,
        "expires": expires,
        "used_by": {},
        "created_at": datetime.now().isoformat()
    }
    
    if save_promocode(code, data):
        bot.reply_to(message, f"✅ Промокод `{code}` создан!\nСкидка: {discount} {promo_type}")
    else:
        bot.reply_to(message, "❌ Ошибка")

@bot.message_handler(commands=['add_cookie'])
def add_cookie(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "❌ /add_cookie [cookie_data] [price]")
        return
    
    cookie = parts[1]
    price = float(parts[2])
    
    product = {
        "type": "cookie",
        "data": cookie,
        "price": price,
        "loot": 50,
        "level": "mid",
        "wallet": {"addr": CRYPTO_WALLET, "network": CRYPTO_NETWORK},
        "stats": {"robux": 1000, "items": 5, "age": 2020},
        "createdAt": datetime.now().isoformat()
    }
    
    url = f"{FIREBASE_URL}products.json"
    response = requests.post(url, json=product, proxies={})
    if response.status_code == 200:
        bot.reply_to(message, f"✅ Кука добавлена!\nЦена: {price} USDT")
    else:
        bot.reply_to(message, "❌ Ошибка")

@bot.message_handler(commands=['add_tg'])
def add_tg(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        bot.reply_to(message, "❌ /add_tg [phone] [price] [2fa]")
        return
    
    phone = parts[1]
    price = float(parts[2])
    twofa = parts[3] if len(parts) > 3 else ""
    
    product = {
        "type": "tg",
        "data": phone,
        "price": price,
        "twofa": twofa,
        "loot": 50,
        "level": "mid",
        "wallet": {"addr": CRYPTO_WALLET, "network": CRYPTO_NETWORK},
        "stats": {"sessions": 3, "groups": 5},
        "createdAt": datetime.now().isoformat()
    }
    
    url = f"{FIREBASE_URL}products.json"
    response = requests.post(url, json=product, proxies={})
    if response.status_code == 200:
        bot.reply_to(message, f"✅ TG аккаунт добавлен!\nНомер: {phone}\nЦена: {price} USDT")
    else:
        bot.reply_to(message, "❌ Ошибка")

@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    url_products = f"{FIREBASE_URL}products.json?shallow=true"
    url_users = f"{FIREBASE_URL}users.json?shallow=true"
    
    products_resp = requests.get(url_products, proxies={})
    users_resp = requests.get(url_users, proxies={})
    
    text = "📊 **Статистика**\n\n"
    text += f"👥 Пользователей: {len(users_resp.json()) if users_resp.status_code == 200 else 0}\n"
    text += f"📦 Товаров: {len(products_resp.json()) if products_resp.status_code == 200 else 0}\n"
    text += f"\n💳 Кошелёк: `{CRYPTO_WALLET}`"
    
    bot.reply_to(message, text)

# ======== FLASK WEBHOOK ========
app = Flask(__name__)
CORS(app)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def home():
    return "🤖 CookieBuy Bot is running!"

@app.route('/api/verify_tg_link', methods=['POST'])
def verify_tg_link():
    data = request.json
    uid = data.get('uid')
    if not uid:
        return jsonify({"error": "Missing uid"}), 400
    
    link_data = get_tg_link(uid)
    if not link_data:
        return jsonify({"error": "Link not found"}), 404
    
    expires_at = datetime.fromisoformat(link_data['expires_at'])
    if datetime.now() > expires_at:
        return jsonify({"error": "Link expired"}), 410
    
    if link_data.get('used', False):
        return jsonify({"error": "Link already used"}), 409
    
    tg_data = temp_links.get(uid)
    if not tg_data:
        return jsonify({"error": "Telegram data not found"}), 404
    
    mark_link_used(uid)
    
    return jsonify({
        "success": True,
        "tg_id": tg_data['tg_id'],
        "uid": uid
    })

@app.route('/api/confirm_tg_link', methods=['POST'])
def confirm_tg_link():
    data = request.json
    uid = data.get('uid')
    firebase_uid = data.get('firebase_uid')
    
    if not uid or not firebase_uid:
        return jsonify({"error": "Missing data"}), 400
    
    link_data = get_tg_link(uid)
    if not link_data:
        return jsonify({"error": "Link not found"}), 404
    
    tg_data = temp_links.get(uid)
    if not tg_data:
        return jsonify({"error": "Telegram data not found"}), 404
    
    user = type('User', (), {
        'id': tg_data['tg_id'],
        'username': f"user_{tg_data['tg_id']}",
        'first_name': "Telegram",
        'last_name': "User"
    })
    
    if save_tg_user(firebase_uid, user):
        try:
            bot.send_message(tg_data['tg_id'], "✅ Аккаунт привязан к сайту!")
        except:
            pass
        temp_links.pop(uid, None)
        return jsonify({"success": True})
    
    return jsonify({"error": "Failed to save"}), 500

@app.route('/api/get_tg_code', methods=['POST'])
def get_tg_code():
    data = request.json
    item_id = data.get('item_id')
    user_id = data.get('user_id')
    
    if not item_id or not user_id:
        return jsonify({"error": "Missing data"}), 400
    
    url = f"{FIREBASE_URL}users/{user_id}/inventory/{item_id}.json"
    response = requests.get(url, proxies={})
    if response.status_code != 200 or not response.json():
        return jsonify({"error": "Item not found"}), 404
    
    item = response.json()
    if item.get('status') != 'waiting_code':
        return jsonify({"error": "Item not waiting for code"}), 400
    
    code = generate_tg_code()
    pending_codes[item_id] = {
        'user_id': user_id,
        'code': code,
        'expires': datetime.now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
    }
    
    url_code = f"{FIREBASE_URL}users/{user_id}/inventory/{item_id}/code.json"
    requests.put(url_code, json=code, proxies={})
    
    return jsonify({"success": True, "code": code})

@app.route('/api/apply_promo', methods=['POST'])
def apply_promo():
    data = request.json
    code = data.get('code')
    user_id = data.get('user_id')
    
    if not code or not user_id:
        return jsonify({"error": "Missing data"}), 400
    
    promo = get_promocode(code.upper())
    if not promo:
        return jsonify({"error": "Promocode not found"}), 404
    
    if 'expires' in promo:
        expires = datetime.fromisoformat(promo['expires'])
        if datetime.now() > expires:
            return jsonify({"error": "Promocode expired"}), 410
    
    if user_id in promo.get('used_by', {}):
        return jsonify({"error": "Already used"}), 409
    
    return jsonify({
        "success": True,
        "discount": promo.get('discount', 0),
        "type": promo.get('type', 'percent')
    })

@app.route('/api/wallet', methods=['GET'])
def get_wallet():
    return jsonify({
        "address": CRYPTO_WALLET,
        "network": CRYPTO_NETWORK
    })

# ======== ЗАПУСК ========
if __name__ == "__main__":
    def run_bot():
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"❌ Бот остановлен: {e}")
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    print("=" * 50)
    print("🤖 COOKIEBUY БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"💳 Кошелёк: {CRYPTO_WALLET}")
    print(f"🌐 Сеть: {CRYPTO_NETWORK}")
    print(f"📱 Сайт: {SITE_URL}")
    print(f"📏 Длина кода: {CODE_LENGTH} цифр")
    print(f"⏳ Код действует: {CODE_EXPIRY_MINUTES} минут")
    print("=" * 50)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
