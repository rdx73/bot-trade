import requests, pandas as pd, random, json, os
from datetime import datetime, timedelta, timezone

# ====== CONFIG (ENV) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
API_KEY   = os.getenv("API_KEY")

PASTEBIN_RAW_URL     = os.getenv("PASTEBIN_RAW_URL")
PAIR_LIST = [p.strip() for p in os.getenv("PAIR_LIST", "EUR/USD").split(",")]

_min_conf = os.getenv("MIN_CONFIDENCE", "").strip()
MIN_CONFIDENCE = int(_min_conf) if _min_conf.isdigit() else 70

DEBUG_MODE = os.getenv("DEBUG_MODE", "1") == "1"

if not all([BOT_TOKEN, CHAT_ID, API_KEY, PASTEBIN_RAW_URL]):
    raise Exception("❌ ENV missing, check GitHub Secrets")

# ====== TIMEZONE ======
WIB = timezone(timedelta(hours=7))
def now_wib():
    return datetime.now(timezone.utc).astimezone(WIB)

<<<<<<< HEAD
# ====== M30 TIMING (FIXED) ======
def valid_m30_time():
    # toleransi GitHub Actions (0–2 & 30–32)
=======
# ====== M30 TIMING ======
def valid_m30_time():
>>>>>>> ff65ab3 (Update bot.py: lebih responsif + Demand Zone strategy)
    return now_wib().minute % 30 < 3

# ====== TELEGRAM ======
def send_telegram(text):
    import urllib.parse
    text_enc = urllib.parse.quote(text)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text_enc}"
    try:
        r = requests.get(url, timeout=10)
        print("Telegram:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

# ====== MEMORY ======
def load_memory():
    try:
        r = requests.get(PASTEBIN_RAW_URL, timeout=10)
        if r.status_code == 200:
            return json.loads(r.text)
    except Exception as e:
        print("Memory load error:", e)
    return {}

memory = load_memory()

# ====== MARKET DATA ======
def get_market_data(pair):
    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": pair,
                "interval": "30min",
                "outputsize": 120,
                "apikey": API_KEY
            },
            timeout=15
        )
        data = r.json()
        if "values" not in data:
            print("No data for", pair, data)
            return None
        df = pd.DataFrame(data["values"])
        df = df.iloc[::-1].reset_index(drop=True)
        for c in ["close","high","low"]:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        print("Market data error:", e)
        return None

# ====== ANALYSIS ======
def analyze(pair):
    df = get_market_data(pair)
    if df is None or len(df) < 60:
        return None

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
    df["tr"] = df[["high","low","close"]].apply(
        lambda x: max(
            x["high"] - x["low"],
            abs(x["high"] - x["close"]),
            abs(x["low"] - x["close"])
        ), axis=1
    )
    df["atr"] = df["tr"].rolling(14).mean()

    last_price = df["close"].iloc[-1]
    atr = df["atr"].iloc[-1]

    # Trend
    trend = "UP" if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1] else "DOWN"
    rsi_val = df["rsi"].iloc[-1]

    if rsi_val < 35:
        rsi_zone = "OVERSOLD"
    elif rsi_val > 65:
        rsi_zone = "OVERBOUGHT"
    else:
        rsi_zone = "NORMAL"

    # Demand Zone (Support/Resistance)
    recent_low = df["low"].iloc[-20:].min()
    recent_high = df["high"].iloc[-20:].max()

    dz_signal = None
    if last_price <= recent_low * 1.002:  # dekat support
        dz_signal = "BUY"
    elif last_price >= recent_high * 0.998:  # dekat resistance
        dz_signal = "SELL"

    state = f"{trend}_{rsi_zone}"
    memory.setdefault(state, {"BUY":1, "SELL":1, "WAIT":1})

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

    # Demand Zone Boost
    if dz_signal == "BUY":
        confidence += 15
        reason.append("Near demand zone (support) → BUY bias")
    elif dz_signal == "SELL":
        confidence += 15
        reason.append("Near resistance zone → SELL bias")

    # Randomized minor boost (responsiveness)
    confidence += random.randint(0,5)

    # Decide action
    action = max(memory[state], key=memory[state].get)
    if confidence >= MIN_CONFIDENCE:
        action = dz_signal if dz_signal else action
    else:
        # responsif: peluang kecil ambil action walau confidence rendah
        if dz_signal and random.random() < 0.5:  # 50% probabilitas
            action = dz_signal
        else:
            action = "WAIT"

    tp = sl = None
    if action == "BUY":
        tp = last_price + atr*1.5
        sl = last_price - atr*1.0
    elif action == "SELL":
        tp = last_price - atr*1.5
        sl = last_price + atr*1.0

    return action, confidence, reason, state, tp, sl

# ====== MAIN ======
def main():
    t = now_wib().strftime("%Y-%m-%d %H:%M")
    send_telegram(f"🚀 Bot started & running\nTIME: {t} WIB")

    if not valid_m30_time():
        msg = (
            "⏳ BOT CHECK\n"
            "STATUS: Not M30 close yet\n"
            f"TIME: {t} WIB"
        )
        print(msg)
        send_telegram(msg)
        return

    for pair in PAIR_LIST:
        result = analyze(pair)
        if not result:
            continue

        action, confidence, reason, state, tp, sl = result

        msg = (
            f"PAIR: {pair}\n"
            f"TF: 30M\n"
            f"SIGNAL: {action}\n"
            f"CONFIDENCE: {confidence}% (min {MIN_CONFIDENCE}%)\n"
            f"STATE: {state}\n"
            f"REASON:\n- " + "\n- ".join(reason)
        )

        if tp and sl:
            msg += f"\nTP: {tp:.5f}\nSL: {sl:.5f}\nHOLD: 30–120 menit"

        msg += f"\nTIME: {t} WIB"

        if action == "WAIT":
            msg = "⏸ WAIT SIGNAL\n" + msg

        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    main()
