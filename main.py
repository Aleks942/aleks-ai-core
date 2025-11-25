import os
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    requests.post(url, json=payload)

def analyze_signal(symbol, price, volume, trend):
    score = 0

    if trend == "up":
        score += 2
    if volume > 1.5:
        score += 2
    if price > 0:
        score += 1

    if score >= 4:
        return "STRONG BUY"
    elif score == 3:
        return "BUY"
    elif score == 2:
        return "NEUTRAL"
    else:
        return "SELL"

def handle_webhook(data):
    symbol = data.get("symbol")
    price = float(data.get("price", 0))
    volume = float(data.get("volume", 1))
    trend = data.get("trend", "neutral")

    result = analyze_signal(symbol, price, volume, trend)

    send_message(f"Signal: {symbol}\nResult: {result}\nPrice: {price}")

    return {"status": "ok", "result": result}
