import os
import time
from pybit.unified_trading import HTTP
from telegram.ext import Updater, MessageHandler, Filters

BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_SECRET = os.environ.get("BYBIT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

FIXED_USDT = 100
LEVERAGE = 10
MAX_REENTRIES = 2

session = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_SECRET
)

def parse_signal(text):
    lines = text.strip().split("\n")
    symbol, side = lines[0].split()
    entry = float(lines[1])
    sl = float(lines[2])
    tps = [float(x) for x in lines[3:]]
    return symbol.upper(), side.lower(), entry, sl, tps

def calculate_qty(symbol):
    ticker = session.get_tickers(category="linear", symbol=symbol)
    price = float(ticker['result']['list'][0]['lastPrice'])
    qty = (FIXED_USDT * LEVERAGE) / price
    return round(qty, 3)

def market_order(symbol, side, qty, reduce=False):
    order_side = "Buy" if side == "long" else "Sell"
    if reduce:
        order_side = "Sell" if side == "long" else "Buy"

    session.place_order(
        category="linear",
        symbol=symbol,
        side=order_side,
        orderType="Market",
        qty=round(qty, 3),
        reduceOnly=reduce
    )

def set_stop(symbol, sl):
    session.set_trading_stop(
        category="linear",
        symbol=symbol,
        stopLoss=str(sl),
        positionIdx=0
    )

def monitor_trade(symbol, side, entry, sl, tps):
    qty = calculate_qty(symbol)
    market_order(symbol, side, qty)
    set_stop(symbol, sl)

    reentries = 0
    tp_hit = [False] * len(tps)
    part = qty / len(tps)

    while True:
        ticker = session.get_tickers(category="linear", symbol=symbol)
        price = float(ticker['result']['list'][0]['lastPrice'])

        for i, tp in enumerate(tps):
            if not tp_hit[i]:
                if (side == "short" and price <= tp) or (side == "long" and price >= tp):
                    market_order(symbol, side, part, reduce=True)
                    tp_hit[i] = True

                    if i == 0:
                        set_stop(symbol, entry)

        if all(tp_hit):
            break

        if tp_hit[0] and reentries < MAX_REENTRIES:
            if (side == "short" and price >= entry) or (side == "long" and price <= entry):
                market_order(symbol, side, qty)
                reentries += 1

        time.sleep(3)

def handle_signal(update, context):
    try:
        symbol, side, entry, sl, tps = parse_signal(update.message.text)
        update.message.reply_text("Сигнал принят.")
        monitor_trade(symbol, side, entry, sl, tps)
        update.message.reply_text("Сделка завершена.")
    except Exception as e:
        update.message.reply_text(f"Ошибка: {e}")

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text, handle_signal))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
