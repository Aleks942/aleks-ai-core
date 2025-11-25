import requests
from statistics import mean

# ====== ТВОИ НАСТРОЙКИ ======
TELEGRAM_TOKEN = "8473865365:AAH4biKKokz6Io23ZkqBuO7Q0HnzTdXCT9o"
TELEGRAM_CHAT_ID = "851440772"


# ====== ОТПРАВКА СООБЩЕНИЯ ======
def send_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        print("Telegram error:", e)


# ====== АНАЛИЗ ======
def analyze_signal(symbol, price, volume, trend, history):
    """
    Ядро ИИ: принимает данные и выдаёт готовый трейдинг-сигнал.
    
    history — список последних цен (для анализа волатильности, разворотов, паттернов)
    """

    score = 0
    reasons = []

    # --- 1. Цена: пробой уровней, импульсы, откаты ---
    if len(history) >= 3:
        last = history[-1]
        prev = history[-2]

        # импульс вверх
        if last > prev * 1.005:
            score += 1
            reasons.append("Импульс вверх")

        # импульс вниз
        if last < prev * 0.995:
            score -= 1
            reasons.append("Импульс вниз")

    # --- 2. Тренд (MA, EMA и т.п. — приходит из TradingView) ---
    if trend == "up":
        score += 2
        reasons.append("Восходящий тренд")
    elif trend == "down":
        score -= 2
        reasons.append("Нисходящий тренд")

    # --- 3. Объёмы ---
    if volume > 1:
        score += 2
        reasons.append("Высокий объём")
    elif volume < 0.6:
        score -= 1
        reasons.append("Слабый объём")

    # --- 4. Волатильность ---
    if len(history) >= 5:
        vol = max(history[-5:]) - min(history[-5:])
        if vol > price * 0.01:
            score += 1
            reasons.append("Высокая волатильность")

    # ====== РЕЗУЛЬТАТ ======
    if score >= 4:
        signal = "STRONG BUY"
    elif score >= 2:
        signal = "BUY"
    elif score <= -4:
        signal = "STRONG SELL"
    elif score <= -2:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    message = (
        f"Сигнал по {symbol}\n"
        f"Тип: {signal}\n"
        f"Цена: {price}\n"
        f"Причины: {', '.join(reasons) if reasons else 'Нет данных'}"
    )

    return message, signal


# ====== ПРИЁМ ВЕБХУКА ОТ TRADINGVIEW ======
def handle_webhook(data):
    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0))
    volume = float(data.get("volume", 1))
    trend = data.get("trend", "neutral")
    history = data.get("history", [])

    msg, signal = analyze_signal(symbol, price, volume, trend, history)
    send_message(msg)

    return {"status": "ok", "signal": signal}


# ====== СТАРТ СЕРВЕРА ДЛЯ RENDER ======
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route("/signal", methods=["POST"])
def signal():
    data = request.json
    result = handle_webhook(data)
    return jsonify(result)


@app.route("/", methods=["GET"])
def home():
    return "Aleks AI Core работает!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
