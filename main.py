from flask import Flask, request, jsonify
import requests
import os

# ---------------------------------------------------------
# Создаём Flask приложение
# ---------------------------------------------------------

app = Flask(__name__)

# ---------------------------------------------------------
# Главная проверка — работает ли сервер
# ---------------------------------------------------------

@app.route('/')
def home():
    return "Alek AI Core работает!"

# ---------------------------------------------------------
# Webhook для TradingView
# ---------------------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    if not data:
        return jsonify({"status": "error", "message": "empty"}), 400

    # Чтение данных
    symbol = data.get("symbol", "???")
    price = data.get("price", "???")
    volume = data.get("volume", "???")
    trend = data.get("trend", "???")

    # Сообщение
    msg = f"""
🔔 Сигнал от TradingView
Актив: {symbol}
Цена: {price}
Объём: {volume}
Тренд: {trend}
    """

    send_telegram(msg)

    return jsonify({"status": "ok"}), 200

# ---------------------------------------------------------
# Отправка сообщений в Telegram
# ---------------------------------------------------------

def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    requests.post(url, json=payload)

# ---------------------------------------------------------
# Запуск приложения
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

