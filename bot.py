import requests, pandas as pd, datetime, random, json, os, time

# ====== CONFIG (ENV) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
API_KEY   = os.getenv("API_KEY")

if not BOT_TOKEN or not CHAT_ID or not API_KEY:
    raise Exception("ENV missing: BOT_TOKEN / CHAT_ID / API_KEY")

PAIR = "EUR/USD"
TF   = "M30"

# ====== FILES ======
MEMORY_FILE = "memory.json"
CONF_FILE   = "confidence.json"
EQUITY_FILE = "equity.json"

# ====== INIT FILES ======
for f, default in [
    (MEMORY_FILE, {}),
    (CONF_FILE, {"min_confidence": 70}),
    (EQUITY_FILE, {"balance": 1000.0, "history": []})
]:
    if not os.path.exists(f):
        json.dump(default, open(f, "w"))

memory = json.load(open(MEMORY_FILE))
conf   = json.load(open(CONF_FILE))
equity = json.load(open(EQUITY_FILE))

# ====== TELEGRAM ======
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

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

    if data.get("status") == "error":
        print("TwelveData ERROR:", data)
        return None

    if "values" not in data:
        print("Invalid API response:", data)
        return None

    df = pd.DataFrame(data["values"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== ANALYSIS ======
def analyze():
    df = get_market_data()
    if df is None or len(df) < 60:
        return "WAIT", 0, ["Market data unavailable"], "NO_DATA", None, None, None

    # EMA & RSI
    df["ema_fast"] = df["close"].ewm(span=20).mean()
    df["ema_slow"] = df["close"].ewm(span=50).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR untuk TP/SL
    df["tr"] = df[["high","low","close"]].apply(
        lambda x: max(
            x["high"]-x["low"],
            abs(x["high"]-x["close"]),
            abs(x["low"]-x["close"])
        ), axis=1
    )
    df["atr"] = df["tr"].rolling(14).mean()
    last_atr = df["atr"].iloc[-1]
    last_price = df["close"].iloc[-1]

    trend = "UP" if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1] else "DOWN"

    if df["rsi"].iloc[-1] < 35:
        rsi_zone = "OVERSOLD"
    elif df["rsi"].iloc[-1] > 65:
        rsi_zone = "OVERBOUGHT"
    else:
        rsi_zone = "NORMAL"

    state = f"{trend}_{rsi_zone}"

    if state not in memory:
        memory[state] = {"BUY": 1, "SELL": 1, "WAIT": 1}

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
    action = max(memory[state], key=memory[state].get)
    if random.random() < 0.05:
        action = random.choice(["BUY","SELL","WAIT"])
    if confidence < conf["min_confidence"]:
        action = "WAIT"

    # TP, SL, Durasi
    if action == "BUY":
        tp = last_price + last_atr * 1.5
        sl = last_price - last_atr * 1.0
    elif action == "SELL":
        tp = last_price - last_atr * 1.5
        sl = last_price + last_atr * 1.0
    else:
        tp = sl = None

    hold_time_min = 30
    hold_time_max = 120
    return action, confidence, reason, state, tp, sl, (hold_time_min, hold_time_max)

# ====== UPDATE LEARNING ======
def update_learning(action, tp, sl):
    if action == "WAIT" or tp is None or sl is None:
        return

    df = get_market_data()
    if df is None or len(df) == 0:
        return

    last_price = df["close"].iloc[-1]

    status = None
    profit = 0.0

    if action == "BUY":
        if last_price >= tp:
            status = "WIN"
            profit = tp - df["close"].iloc[-2]
        elif last_price <= sl:
            status = "LOSS"
            profit = sl - df["close"].iloc[-2]
    elif action == "SELL":
        if last_price <= tp:
            status = "WIN"
            profit = df["close"].iloc[-2] - tp
        elif last_price >= sl:
            status = "LOSS"
            profit = df["close"].iloc[-2] - sl

    if status:
        # Kirim notifikasi
        msg = f"⚡ TP/SL Triggered ⚡\nPAIR: {PAIR}\nACTION: {action}\nRESULT: {status}\nPROFIT: {profit:.5f}\nTIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        send_telegram(msg)

        # Update memory & equity
        state = f"{'UP' if action=='BUY' else 'DOWN'}_NORMAL"
        if state not in memory:
            memory[state] = {"BUY": 1, "SELL": 1, "WAIT": 1}

        if status == "WIN":
            memory[state][action] += 1
            conf["min_confidence"] = max(60, conf["min_confidence"] - 1)
        else:
            memory[state][action] -= 1
            conf["min_confidence"] = min(85, conf["min_confidence"] + 2)

        equity["balance"] += profit
        equity["history"].append({
            "time": datetime.datetime.now().isoformat(),
            "result": status,
            "profit": profit,
            "balance": equity["balance"]
        })

        json.dump(memory, open(MEMORY_FILE, "w"), indent=2)
        json.dump(conf, open(CONF_FILE, "w"), indent=2)
        json.dump(equity, open(EQUITY_FILE, "w"), indent=2)

# ====== MAIN ======
def main():
    action, confidence, reason, state, tp, sl, hold = analyze()

    msg = (
        f"PAIR: {PAIR}\nTF: {TF}\nSIGNAL: {action}\nCONFIDENCE: {confidence}% (min {conf['min_confidence']}%)\nSTATE: {state}\n"
        f"REASON:\n- " + "\n- ".join(reason)
    )

    if tp and sl:
        msg += f"\nTP: {tp:.5f}\nSL: {sl:.5f}\nHOLD: {hold[0]}-{hold[1]} menit"

    msg += f"\nTIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

    print(msg)

    if action != "WAIT":
        send_telegram(msg)
        update_learning(action, tp, sl)

if __name__ == "__main__":
    main()
