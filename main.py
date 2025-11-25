from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Главная проверка — работает ли сервер
@app.route('/')
def home():
    return "Aleks AI Core работает!"

# ==== WEBHOOK для TradingView ====
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    # Проверка — пришли ли данные
    if not data:
        return jsonify({"status": "error", "message": "нет данных"}), 400

    # Сообщение в Telegram
    TELEGRAM_TOKEN = "8473865365:AAH4biK0Kz6Io23ZkqBu07Q0HmzTdXCT9o"
    TELEGRAM_CHAT_ID = "851440772"

    text = f"Новый сигнал:\n{data}"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    requests.post(url, json=payload)

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
