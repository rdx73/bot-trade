import bot
from datetime import datetime, timezone, timedelta

# ===== TIMEZONE WIB =====
WIB = timezone(timedelta(hours=7))
def now_wib():
    return datetime.now(timezone.utc).astimezone(WIB)

# ===== Waktu sekarang =====
t = now_wib().strftime("%Y-%m-%d %H:%M")
print(f"⏱ Checking DZ signals at {t} WIB")

# ===== LOOP per PAIR =====
for pair in bot.PAIR_LIST:
    df = bot.get_market_data(pair)
    if df is None or len(df) < 20:
        print(f"{pair} | No sufficient data")
        continue

    last_price = df['close'].iloc[-1]
    recent_low = df['low'].iloc[-20:].min()
    recent_high = df['high'].iloc[-20:].max()

    dz_signal = None
    if last_price <= recent_low * 1.002:
        dz_signal = "BUY"
    elif last_price >= recent_high * 0.998:
        dz_signal = "SELL"

    msg = (
        f"PAIR: {pair}\n"
        f"Last Close: {last_price}\n"
        f"Recent Low: {recent_low}\n"
        f"Recent High: {recent_high}\n"
        f"DZ SIGNAL: {dz_signal if dz_signal else 'WAIT'}\n"
        f"TIME: {t} WIB"
    )
    print(msg)
