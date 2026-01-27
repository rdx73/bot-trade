import requests, pandas as pd, random, json, os
from datetime import datetime, timedelta, timezone

# ====== CONFIG (ENV) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
API_KEY   = os.getenv("API_KEY")
PASTEBIN_RAW_URL = os.getenv("PASTEBIN_RAW_URL")

if not BOT_TOKEN or not CHAT_ID or not API_KEY or not PASTEBIN_RAW_URL:
    raise Exception("ENV missing: BOT_TOKEN / CHAT_ID / API_KEY / PASTEBIN_RAW_URL")

PAIR = "EUR/USD"
TF   = "M30"

# ====== TIMEZONE ======
WIB = timezone(timedelta(hours=7))

def now_wib():
    return datetime.now(timezone.utc).astimezone(WIB)

# ====== CONF ======
MIN_CONFIDENCE = 70

# ====== TELEGRAM ======
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ====== LOAD MEMORY FROM PASTEBIN ======
def load_memory():
    try:
        r = requests.get(PASTEBIN_RAW_URL, timeout=10)
        data = r.json()
        if not isinstance(data, dict):
            raise Exception("Invalid memory format")
        return data
    except Exception as e:
        print("Pastebin memory load failed:", e)
        return {}

# ====== MARKET DATA ======
def get_market_data():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": PAIR,
        "interval": "30min",
        "outputsize": 120,
        "apikey": API_KEY
    }
    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    if data.get("status") == "error" or "values" not in data:
        print("TwelveData ERROR:", data)
        return None

    df = pd.DataFrame(data["values"])
    for c in ["close", "high", "low"]:
        df[c] = df[c].astype(float)

    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== ANALYSIS ======
def analyze():
    df = get_market_data()
    if df is None or len(df) < 60:
        return "WAIT", 0, ["Market data unavailable"], "NO_DATA", None, None, None

    memory = load_memory()

    # EMA
    df["ema_fast"] = df["close"].ewm(span=20).mean()
    df["ema_slow"] = df["close"].ewm(span=50).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    df["tr"] = df[["high", "low", "close"]].apply(
        lambda x: max(
            x["high"] - x["low"],
            abs(x["high"] - x["close"]),
            abs(x["low"] - x["close"])
        ), axis=1
    )
    df["atr"] = df["tr"].rolling(14).mean()

    last_price = df["close"].iloc[-1]
    last_atr   = df["atr"].iloc[-1]

    trend = "UP" if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1] else "DOWN"

    if df["rsi"].iloc[-1] < 35:
        rsi_zone = "OVERSOLD"
    elif df["rsi"].iloc[-1] > 65:
        rsi_zone = "OVERBOUGHT"
    else:
        rsi_zone = "NORMAL"

    state = f"{trend}_{rsi_zone}"

    confidence = 40
    reason = ["EMA trend confirmed"]

    if rsi_zone == "NORMAL":
        confidence += 30
        reason.append("RSI normal zone")
    elif rsi_zone == "OVERSOLD" and trend == "UP":
        confidence += 20
        reason.append("RSI oversold in uptrend")
    elif rsi_zone == "OVERBOUGHT" and trend == "DOWN":
        confidence += 20
        reason.append("RSI overbought in downtrend")

    confidence += random.randint(0, 5)

    state_pref = memory.get(state, {"BUY": 1, "SELL": 1, "WAIT": 1})
    action = max(state_pref, key=state_pref.get)

    if confidence < MIN_CONFIDENCE:
        action = "WAIT"

    if action == "BUY":
        tp = last_price + last_atr * 1.5
        sl = last_price - last_atr * 1.0
    elif action == "SELL":
        tp = last_price - last_atr * 1.5
        sl = last_price + last_atr * 1.0
    else:
        tp = sl = None

    return action, confidence, reason, state, tp, sl, (30, 120)

# ====== MAIN ======
def main():
    action, confidence, reason, state, tp, sl, hold = analyze()
    wib_now = now_wib()

    msg = (
        f"PAIR: {PAIR}\nTF: {TF}\nSIGNAL: {action}\n"
        f"CONFIDENCE: {confidence}% (min {MIN_CONFIDENCE}%)\n"
        f"STATE: {state}\nREASON:\n- " + "\n- ".join(reason)
    )

    if tp and sl:
        msg += f"\nTP: {tp:.5f}\nSL: {sl:.5f}\nHOLD: {hold[0]}-{hold[1]} menit"

    msg += f"\nTIME: {wib_now.strftime('%Y-%m-%d %H:%M')} WIB"

    print(msg)

    if action != "WAIT":
        send_telegram(msg)

if __name__ == "__main__":
    main()