import bot
from datetime import datetime, timezone, timedelta

# WIB timezone
WIB = timezone(timedelta(hours=7))
def now_wib():
    return datetime.now(timezone.utc).astimezone(WIB)

t = now_wib().strftime("%Y-%m-%d %H:%M")
print(f"⏱ Checking at {t} WIB")

# Cek M30 close
if bot.valid_m30_time():
    print("✅ M30 close detected, running analysis...")
    for pair in bot.PAIR_LIST:
        result = bot.analyze(pair)
        if not result:
            continue
        action, confidence, reason, state, tp, sl = result

        dz_signal = None
        df = bot.get_market_data(pair)
        if df is not None:
            last_price = df['close'].iloc[-1]
            recent_low = df['low'].iloc[-20:].min()
            recent_high = df['high'].iloc[-20:].max()
            if last_price <= recent_low * 1.002:
                dz_signal = "BUY"
            elif last_price >= recent_high * 0.998:
                dz_signal = "SELL"

        msg = (
            f"PAIR: {pair}\n"
            f"TF: 30M\n"
            f"SIGNAL: {action}\n"
            f"CONFIDENCE: {confidence}% (min {bot.MIN_CONFIDENCE}%)\n"
            f"STATE: {state}\n"
            f"REASON:\n- " + "\n- ".join(reason)
        )
        if tp and sl:
            msg += f"\nTP: {tp:.5f}\nSL: {sl:.5f}\nHOLD: 30–120 menit"
        if dz_signal:
            msg += f"\nDZ SIGNAL: {dz_signal}"
        msg += f"\nTIME: {t} WIB"
        print(msg)
else:
    print("⏳ Not M30 close yet, skipping analysis.")
