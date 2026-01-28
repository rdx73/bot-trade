import requests, pandas as pd, random, json, os, time
from datetime import datetime, timedelta, timezone

# ====== CONFIG (ENV) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
API_KEY   = os.getenv("API_KEY")
PASTEBIN_API_DEV_KEY = os.getenv("PASTEBIN_API_DEV_KEY")
PASTEBIN_USERNAME    = os.getenv("PASTEBIN_USERNAME")
PASTEBIN_PASSWORD    = os.getenv("PASTEBIN_PASSWORD")
PASTEBIN_RAW_URL     = os.getenv("PASTEBIN_RAW_URL")  # URL raw memory.json
PAIR_LIST             = os.getenv("PAIR_LIST", "EUR/USD").split(",")
MIN_CONFIDENCE        = int(os.getenv("MIN_CONFIDENCE", "70"))
DEBUG_MODE            = os.getenv("DEBUG_MODE", "1") == "1"

if not all([BOT_TOKEN, CHAT_ID, API_KEY, PASTEBIN_API_DEV_KEY, PASTEBIN_USERNAME, PASTEBIN_PASSWORD, PASTEBIN_RAW_URL]):
    raise Exception("ENV missing: check all required secrets!")

# ====== TIMEZONE ======
WIB = timezone(timedelta(hours=7))
def now_wib():
    return datetime.now(timezone.utc).astimezone(WIB)

# ====== TELEGRAM ======
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ====== PASTEBIN ======
def pastebin_login():
    url = "https://pastebin.com/api/api_login.php"
    data = {
        "api_dev_key": PASTEBIN_API_DEV_KEY,
        "api_user_name": PASTEBIN_USERNAME,
        "api_user_password": PASTEBIN_PASSWORD
    }
    r = requests.post(url, data=data, timeout=15)
    if r.status_code == 200 and "Bad API request" not in r.text:
        return r.text.strip()  # api_user_key
    return None

def load_memory():
    try:
        r = requests.get(PASTEBIN_RAW_URL, timeout=15)
        if r.status_code == 200:
            mem = json.loads(r.text)
            return mem
    except:
        pass
    return {}

def save_memory_to_pastebin(memory_dict, api_user_key):
    url = "https://pastebin.com/api/api_post.php"
    data = {
        "api_dev_key": PASTEBIN_API_DEV_KEY,
        "api_user_key": api_user_key,
        "api_option": "paste",
        "api_paste_code": json.dumps(memory_dict, indent=2),
        "api_paste_private": 1,
        "api_paste_name": "memory.json",
        "api_paste_expire_date": "N"
    }
    r = requests.post(url, data=data, timeout=15)
    if r.status_code == 200:
        print("Memory updated to Pastebin:", r.text)

# ====== INIT ======
memory = load_memory()
equity = {"balance": 1000.0, "history": []}

# ====== MARKET DATA ======
def get_market_data(pair):
    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": pair, "interval": "30min", "outputsize": 120, "apikey": API_KEY}
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        print("TwelveData ERROR:", data)
        return None
    df = pd.DataFrame(data["values"])
    df["close"] = df["close"].astype(float)
    df["high"]  = df["high"].astype(float)
    df["low"]   = df["low"].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== ANALYSIS ======
def analyze(pair):
    df = get_market_data(pair)
    if df is None or len(df) < 60:
        return "WAIT", 0, ["Market data unavailable"], "NO_DATA", None, None, (30,120)

    df["ema_fast"] = df["close"].ewm(span=20).mean()
    df["ema_slow"] = df["close"].ewm(span=50).mean()
    delta = df["close"].diff()
    gain  = delta.where(delta>0,0)
    loss  = -delta.where(delta<0,0)
    rs    = gain.rolling(14).mean()/loss.rolling(14).mean()
    df["rsi"] = 100-(100/(1+rs))
    df["tr"] = df[["high","low","close"]].apply(lambda x: max(x["high"]-x["low"], abs(x["high"]-x["close"]), abs(x["low"]-x["close"])), axis=1)
    df["atr"] = df["tr"].rolling(14).mean()

    last_price = df["close"].iloc[-1]
    last_atr = df["atr"].iloc[-1]

    trend = "UP" if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1] else "DOWN"
    rsi_zone = "NORMAL"
    if df["rsi"].iloc[-1] < 35: rsi_zone="OVERSOLD"
    elif df["rsi"].iloc[-1] > 65: rsi_zone="OVERBOUGHT"

    state = f"{trend}_{rsi_zone}"
    memory.setdefault(state, {"BUY":1,"SELL":1,"WAIT":1})

    confidence = 40
    reason = ["EMA trend confirmed"]
    if rsi_zone=="NORMAL":
        confidence+=30
        reason.append("RSI normal zone")
    elif rsi_zone=="OVERSOLD" and trend=="UP":
        confidence+=20
        reason.append("RSI oversold in uptrend")
    elif rsi_zone=="OVERBOUGHT" and trend=="DOWN":
        confidence+=20
        reason.append("RSI overbought in downtrend")
    confidence += random.randint(0,5)

    action = max(memory[state], key=memory[state].get)
    if random.random()<0.05:
        action = random.choice(["BUY","SELL","WAIT"])
    if confidence < MIN_CONFIDENCE:
        action="WAIT"

    tp, sl = None, None
    if action=="BUY":
        tp = last_price + last_atr*1.5
        sl = last_price - last_atr*1.0
    elif action=="SELL":
        tp = last_price - last_atr*1.5
        sl = last_price + last_atr*1.0

    if DEBUG_MODE:
        print(f"===== DEBUG INFO =====\nPair: {pair}\nLast Price: {last_price:.5f}\nEMA Fast: {df['ema_fast'].iloc[-1]:.5f}, EMA Slow: {df['ema_slow'].iloc[-1]:.5f}")
        print(f"RSI: {df['rsi'].iloc[-1]:.2f}, ATR: {last_atr:.5f}\nTrend: {trend}, RSI Zone: {rsi_zone}")
        print("Memory Probabilities:", memory[state])
        print(f"Chosen Action: {action}, Confidence: {confidence}%")
        if tp and sl:
            print(f"TP: {tp:.5f}, SL: {sl:.5f}")

    return action, confidence, reason, state, tp, sl, (30,120)

# ====== UPDATE LEARNING ======
def update_learning(action,tp,sl):
    if action=="WAIT": return
    df=get_market_data(PAIR_LIST[0])  # optional: could store last df per pair
    if df is None or len(df)<2: return
    last_price = df["close"].iloc[-1]
    prev_price = df["close"].iloc[-2]

    status = None
    profit = 0.0
    if action=="BUY":
        if last_price>=tp: status="WIN"; profit=tp-prev_price
        elif last_price<=sl: status="LOSS"; profit=sl-prev_price
    elif action=="SELL":
        if last_price<=tp: status="WIN"; profit=prev_price-tp
        elif last_price>=sl: status="LOSS"; profit=prev_price-sl
    if not status: return

    wib_now = now_wib()
    send_telegram(f"⚡ TP/SL Triggered ⚡\nPAIR:{PAIR_LIST[0]}\nACTION:{action}\nRESULT:{status}\nPROFIT:{profit:.5f}\nTIME:{wib_now.strftime('%Y-%m-%d %H:%M')} WIB")

    equity["balance"] += profit
    equity["history"].append({"time":wib_now.isoformat(),"result":status,"profit":profit,"balance":equity["balance"]})

    api_user_key = pastebin_login()
    if api_user_key:
        save_memory_to_pastebin(memory, api_user_key)

# ====== MAIN ======
def main():
    for pair in PAIR_LIST:
        action, confidence, reason, state, tp, sl, hold = analyze(pair)
        wib_now = now_wib()
        msg = (
            f"PAIR:{pair}\nTF:30min\nSIGNAL:{action}\nCONFIDENCE:{confidence}% (min {MIN_CONFIDENCE}%)\nSTATE:{state}\nREASON:\n- " +
            "\n- ".join(reason)
        )
        if tp and sl:
            msg += f"\nTP:{tp:.5f}\nSL:{sl:.5f}\nHOLD:{hold[0]}-{hold[1]} menit"
        msg += f"\nTIME:{wib_now.strftime('%Y-%m-%d %H:%M')} WIB"
        print(msg)
        if action!="WAIT":
            send_telegram(msg)
            update_learning(action,tp,sl)

if __name__=="__main__":
    main()
