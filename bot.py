import requests, pandas as pd, datetime, random, json, os

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
RESULT_FILE = "result.txt"

# ====== INIT FILES ======
if not os.path.exists(MEMORY_FILE):
    json.dump({}, open(MEMORY_FILE, "w"))

if not os.path.exists(CONF_FILE):
    json.dump({"min_confidence": 70}, open(CONF_FILE, "w"))

if not os.path.exists(EQUITY_FILE):
    json.dump({"balance": 1000.0, "history": []}, open(EQUITY_FILE, "w"))

memory = json.load(open(MEMORY_FILE))
conf   = json.load(open(CONF_FILE))
equity = json.load(open(EQUITY_FILE))

# ====== TELEGRAM ======
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=payload, timeout=10)

# ====== MARKET DATA ======
def get_market_data():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": PAIR,
        "interval": "30min",
        "outputsize": 120,
        "apikey": API_KEY
    }

    r = requests.get(url, params=params, timeout=10)
    data = r.json()

    if "values" not in data:
        raise Exception(f"API ERROR: {data}")

    df = pd.DataFrame(data["values"])
    df["close"] = df["close"].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== ANALYSIS ======
def analyze():
    df = get_market_data()

    df["ema_fast"] = df["close"].ewm(span=20).mean()
    df["ema_slow"] = df["close"].ewm(span=50).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    trend = "UP" if last["ema_fast"] > last["ema_slow"] else "DOWN"

    if last["rsi"] < 35:
        rsi_zone = "OVERSOLD"
    elif last["rsi"] > 65:
        rsi_zone = "OVERBOUGHT"
    else:
        rsi_zone = "NORMAL"

    state = f"{trend}_{rsi_zone}"

    if state not in memory:
        memory[state] = {"BUY": 0, "SELL": 0, "WAIT": 0}

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
        action = random.choice(["BUY", "SELL", "WAIT"])

    if confidence < conf["min_confidence"]:
        action = "WAIT"

    return action, confidence, reason, state

# ====== MAIN ======
def main():
    action, confidence, reason, state = analyze()

    msg = (
        f"PAIR: {PAIR}\n"
        f"TF: {TF}\n"
        f"SIGNAL: {action}\n"
        f"CONFIDENCE: {confidence}% (min {conf['min_confidence']}%)\n"
        f"STATE: {state}\n"
        f"REASON:\n- " + "\n- ".join(reason) + "\n"
        f"TIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    if action != "WAIT":
        send_telegram(msg)

    update_learning(state, action)


if __name__ == "__main__":
    main()
