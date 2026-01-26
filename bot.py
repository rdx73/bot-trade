import requests, pandas as pd, datetime, random, json, os, time

# ====== CONFIG ======
BOT_TOKEN = "8224096856:AAGQaxua-UPOyj94xke_Wmec7_xxMmte5WY"
CHAT_ID   = "1373520877"
PAIR = "EURUSD"
TF   = "M5"
SLEEP_SECONDS = 300  # 5 menit

# ====== FILES ======
MEMORY_FILE = "memory.json"
CONF_FILE   = "confidence.json"
EQUITY_FILE = "equity.json"
RESULT_FILE = "result.txt"

# ====== INIT FILES ======
if not os.path.exists(MEMORY_FILE):
    json.dump({}, open(MEMORY_FILE, "w"))

if not os.path.exists(CONF_FILE):
    json.dump({"min_confidence": 65}, open(CONF_FILE, "w"))

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

# ====== MARKET DATA (DEMO) ======
# GANTI NANTI DENGAN DATA REAL (API / CSV)
def get_market_data():
    prices = [100,101,102,101,103,105,104,103,102,101,102,103,104]
    return pd.DataFrame({"close": prices})

# ====== ANALYSIS ======
def analyze():
    df = get_market_data()
    df["ema_fast"] = df["close"].ewm(span=5).mean()
    df["ema_slow"] = df["close"].ewm(span=10).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(7).mean() / loss.rolling(7).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    # State sederhana
    trend = "UP" if last["ema_fast"] > last["ema_slow"] else "DOWN"
    rsi_zone = "LOW" if last["rsi"] < 35 else "HIGH" if last["rsi"] > 65 else "MID"
    state = f"{trend}_{rsi_zone}"

    if state not in memory:
        memory[state] = {"BUY": 0, "SELL": 0, "WAIT": 0}

    # Confidence
    confidence = 0
    reason = []

    if trend == "UP":
        confidence += 40
        reason.append("EMA fast > slow")
    if 30 < last["rsi"] < 70:
        confidence += 30
        reason.append("RSI normal zone")

    confidence += random.randint(0, 10)

    # Action by memory score
    action = max(memory[state], key=memory[state].get)

    # Exploration kecil
    if random.random() < 0.1:
        action = random.choice(["BUY", "SELL", "WAIT"])

    # Confidence adaptive filter
    if confidence < conf["min_confidence"]:
        action = "WAIT"

    return action, confidence, reason, state

# ====== UPDATE FROM RESULT ======
def update_learning(state, action):
    if not os.path.exists(RESULT_FILE):
        return

    content = open(RESULT_FILE).read().strip()
    os.remove(RESULT_FILE)

    status, profit = content.split(",")
    profit = float(profit)

    # Update memory
    if status == "WIN":
        memory[state][action] += 1
        conf["min_confidence"] = max(55, conf["min_confidence"] - 1)
    else:
        memory[state][action] -= 1
        conf["min_confidence"] = min(85, conf["min_confidence"] + 2)

    # Update equity
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

# ====== MAIN LOOP ======
print("AI TELEGRAM STARTED...")
while True:
    try:
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
        time.sleep(SLEEP_SECONDS)

    except Exception as e:
        send_telegram(f"ERROR: {e}")
        time.sleep(60)
