import os
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from statistics import mean

print("=== MOEX INTRADAY RADAR (ACTIVE) 10m+60m: SETUP/ENTRY ===", flush=True)

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# MSK = UTC+3
MSK_OFFSET_HOURS = 3

# ========= SETTINGS =========
CHECK_INTERVAL_SEC = 60 * 3            # чаще, чтобы ловить интрадей
STATE_DIR = os.getenv("STATE_DIR", ".")
STATE_FILE = os.path.join(STATE_DIR, "moex_intraday_state.json")

# Интервалы ISS (минуты)
TF_TRIGGER = 10   # "почти 5-15m" в ISS реальности
TF_FILTER  = 60   # фильтр направления

# Окна анализа
LOOKBACK_10M = 30     # ~5 часов (30*10m)
LOOKBACK_60M = 30     # ~30 часов

# Пороги (ACTIVE)
COOLDOWN_MIN = 30     # быстрее, но без спама

SETUP_RANGE_MAX_PCT = 0.90   # % диапазона (сжатие)
SETUP_VOL_MULT_MIN  = 1.30   # объём растёт

ENTRY_BREAK_PCT_MIN = 0.20   # пробой диапазона на 10m (%)
ENTRY_VOL_MULT_MIN  = 1.50   # объём для входа

# Индекс-фильтр (мягкий)
INDEX_TICKER = "IMOEX"
EMA_PERIOD = 20
INDEX_STRICT = False  # True = резать входы, если индекс против

# Тикеры
BASE_TICKERS = [
    "SBER","GAZP","LKOH","ROSN","GMKN",
    "NVTK","TATN","MTSS","ALRS","CHMF",
    "MAGN","PLZL"
]
PRIORITY_TICKERS = [
    "YNDX","OZON","AFKS","SMLT","PIKK",
    "MOEX","RUAL","FLOT","POLY","SBERP"
]
ALL_TICKERS = list(dict.fromkeys(BASE_TICKERS + PRIORITY_TICKERS))

MOEX = "https://iss.moex.com/iss/engines/stock/markets/shares/securities"

# ========= TELEGRAM =========
def send(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
    except:
        pass

# ========= TIME =========
def msk_now():
    return datetime.now(timezone.utc) + timedelta(hours=MSK_OFFSET_HOURS)

# ========= STATE =========
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_state(state: dict):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except:
        pass

# ========= DATA (robust parse) =========
def get_candles(ticker: str, interval: int, days: int):
    try:
        r = requests.get(
            f"{MOEX}/{ticker}/candles.json",
            params={
                "interval": interval,
                "from": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            },
            timeout=20
        ).json()
        candles = r.get("candles", {})
        cols = candles.get("columns", [])
        data = candles.get("data", [])
        if not cols or not data:
            return [], []
        return cols, data
    except:
        return [], []

def idx(cols, name):
    try:
        return cols.index(name)
    except:
        return None

def series(cols, data, n):
    if not cols or not data:
        return [], [], [], []

    tail = data[-n:] if len(data) >= n else data

    i_close = idx(cols, "close")
    i_high  = idx(cols, "high")
    i_low   = idx(cols, "low")
    i_vol   = idx(cols, "volume")

    highs, lows, closes, vols = [], [], [], []
    for row in tail:
        try:
            close = float(row[i_close]) if i_close is not None and i_close < len(row) and row[i_close] is not None else None
            high  = float(row[i_high])  if i_high  is not None and i_high  < len(row) and row[i_high]  is not None else None
            low   = float(row[i_low])   if i_low   is not None and i_low   < len(row) and row[i_low]   is not None else None
            vol   = float(row[i_vol])   if i_vol   is not None and i_vol   < len(row) and row[i_vol]   is not None else 0.0
        except:
            continue
        if close is None or high is None or low is None:
            continue
        closes.append(close); highs.append(high); lows.append(low); vols.append(vol)

    return highs, lows, closes, vols

def ema_simple(values, period):
    if len(values) < period:
        return None
    return mean(values[-period:])

def pct(a, b):
    if a is None or b is None or b == 0:
        return 0.0
    return (a - b) / b * 100.0

# ========= INDEX FILTER =========
def index_bias():
    cols, data = get_candles(INDEX_TICKER, 24, 220)  # D1
    _, _, closes, _ = series(cols, data, 60)
    if len(closes) < EMA_PERIOD:
        return "FLAT"
    ema = ema_simple(closes, EMA_PERIOD)
    last = closes[-1]
    if ema is None:
        return "FLAT"
    if last > ema * 1.005:
        return "UP"
    if last < ema * 0.995:
        return "DOWN"
    return "FLAT"

# ========= INTRADAY LOGIC =========
def calc_vol_mult(vols):
    if not vols:
        return 0.0
    v_now = vols[-1]
    v_avg = mean(vols[:-1]) if len(vols) > 6 else mean(vols)
    return (v_now / v_avg) if v_avg and v_avg > 0 else 0.0

def detect_setup_entry(ticker: str, idx_dir: str):
    # 10m trigger
    cols10, data10 = get_candles(ticker, TF_TRIGGER, 14)
    h10, l10, c10, v10 = series(cols10, data10, LOOKBACK_10M)
    if len(c10) < LOOKBACK_10M:
        return None

    price = c10[-1]
    hi = max(h10); lo = min(l10)
    rng_pct = (hi - lo) / price * 100.0 if price else 0.0
    vol_mult = calc_vol_mult(v10)

    # 60m filter
    cols60, data60 = get_candles(ticker, TF_FILTER, 45)
    _, _, c60, _ = series(cols60, data60, LOOKBACK_60M)
    if len(c60) < max(6, EMA_PERIOD):
        return None

    ema60 = ema_simple(c60, EMA_PERIOD)
    last60 = c60[-1]
    dir60 = "UP" if ema60 and last60 > ema60 else ("DOWN" if ema60 and last60 < ema60 else "FLAT")

    # direction from last 10m move
    prev10 = c10[-2] if len(c10) >= 2 else c10[-1]
    chg10 = pct(price, prev10)
    dir10 = "UP" if chg10 >= 0 else "DOWN"

    # SETUP
    is_setup = (rng_pct <= SETUP_RANGE_MAX_PCT and vol_mult >= SETUP_VOL_MULT_MIN)

    # ENTRY (пробой диапазона + объём + 60m фильтр)
    break_up = price > hi * (1 + ENTRY_BREAK_PCT_MIN / 100.0)
    break_dn = price < lo * (1 - ENTRY_BREAK_PCT_MIN / 100.0)
    direction = "UP" if break_up else ("DOWN" if break_dn else None)

    idx_ok = True
    if INDEX_STRICT:
        if idx_dir != "FLAT" and direction and idx_dir != direction:
            idx_ok = False

    is_entry = (
        direction is not None and
        vol_mult >= ENTRY_VOL_MULT_MIN and
        dir60 in ("UP","DOWN") and direction == dir60 and
        idx_ok
    )

    # strength 1..5
    strength = 1
    reasons = []

    if is_setup:
        reasons.append(f"Сжатие {rng_pct:.2f}% + объём x{vol_mult:.2f}")
        strength += 1
    if vol_mult >= 1.5:
        strength += 1
    if vol_mult >= 2.2:
        strength += 1

    if direction and direction == dir60:
        reasons.append("10m + 60m в одну сторону")
        strength += 1

    if ticker in PRIORITY_TICKERS:
        reasons.append("Приоритетная бумага")
        strength += 1

    if idx_dir != "FLAT":
        reasons.append(f"IMOEX: {idx_dir}")

    strength = max(1, min(strength, 5))

    return {
        "ticker": ticker,
        "price": price,
        "rng_pct": rng_pct,
        "vol_mult": vol_mult,
        "chg10": chg10,
        "dir60": dir60,
        "idx": idx_dir,
        "is_setup": is_setup,
        "is_entry": is_entry,
        "direction": direction if direction else dir10,
        "strength": strength,
        "reasons": reasons[:10],
    }

def memo():
    return (
        "🕒 <b>Интрадей</b>\n"
        "1) вход только после импульс→пауза→вторая свеча\n"
        "2) стоп за локальный экстремум (10m)\n"
        "3) если нет структуры — SKIP"
    )

# ========= MAIN =========
def run():
    state = load_state()
    per = state.get("per", {})      # per ticker state
    stats = state.get("stats", {"day": msk_now().strftime("%Y-%m-%d"), "setup": 0, "entry": 0})

    # старт 1 раз в сутки
    today = msk_now().strftime("%Y-%m-%d")
    if state.get("start_day") != today:
        send("🇷🇺 <b>MOEX Intraday (ACTIVE)</b>\n10m + 60m • SETUP/ENTRY • быстрый режим • антиспам")
        state["start_day"] = today
        save_state(state)

    while True:
        try:
            now = msk_now()
            day_key = now.strftime("%Y-%m-%d")

            if stats.get("day") != day_key:
                stats = {"day": day_key, "setup": 0, "entry": 0}

            idx_dir = index_bias()
            now_ts = datetime.now(timezone.utc).timestamp()

            for t in ALL_TICKERS:
                ts_last = per.get(t, {}).get("last_ts", 0)
                if ts_last and (now_ts - ts_last) < COOLDOWN_MIN * 60:
                    continue

                s = detect_setup_entry(t, idx_dir)
                if not s:
                    continue

                # анти-дубликат по типу
                last_type = per.get(t, {}).get("last_type")

                # ENTRY приоритетнее SETUP
                if s["is_entry"]:
                    if last_type == "ENTRY":
                        continue

                    msg = (
                        f"🟢 <b>ENTRY</b> (интрадей)\n"
                        f"<b>{t}</b>\n"
                        f"Направление: <b>{s['direction']}</b>\n"
                        f"Сила: {'🔥'*s['strength']} ({s['strength']}/5)\n\n"
                        f"10m: {s['chg10']:.2f}% | 60m фильтр: {s['dir60']}\n"
                        f"Сжатие: {s['rng_pct']:.2f}% | Объём: x{s['vol_mult']:.2f}\n\n"
                        f"Причины:\n• " + "\n• ".join(s["reasons"]) +
                        f"\n\n{memo()}"
                    )
                    send(msg)
                    stats["entry"] += 1

                    per[t] = {"last_ts": now_ts, "last_type": "ENTRY", "last_dir": s["direction"]}
                    continue

                if s["is_setup"]:
                    if last_type == "SETUP":
                        continue

                    msg = (
                        f"🟡 <b>SETUP</b> (интрадей)\n"
                        f"<b>{t}</b>\n"
                        f"Сила: {'🔥'*s['strength']} ({s['strength']}/5)\n\n"
                        f"Сжатие: {s['rng_pct']:.2f}% | Объём: x{s['vol_mult']:.2f}\n"
                        f"60m фильтр: {s['dir60']} | IMOEX: {s['idx']}\n\n"
                        f"Причины:\n• " + "\n• ".join(s["reasons"]) +
                        f"\n\n{memo()}\n\n"
                        f"🧠 <b>ВЫВОД</b>:\nЖдём пробой/отбой уровня. Без структуры — SKIP."
                    )
                    send(msg)
                    stats["setup"] += 1

                    per[t] = {"last_ts": now_ts, "last_type": "SETUP", "last_dir": s["direction"]}

            state["per"] = per
            state["stats"] = stats
            save_state(state)

        except Exception as e:
            send(f"❌ <b>INTRADAY ERROR</b>: {e}")

        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    run()
