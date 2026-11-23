import MetaTrader5 as mt5
import pandas as pd
import logging
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from dotenv import load_dotenv
import os
import sys

from economic_calendar import EconomicCalendar, SOURCES
from mt5_positions import close_bot_positions, immediate_filling_modes, send_with_filling_modes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Trading configuration
symbol = os.getenv("SYMBOL", "").strip()
pip_size = float(os.getenv("PIP_SIZE", 0.01))
stop_loss_pips = float(os.getenv("STOP_LOSS_PIPS", 15)) * pip_size
take_profit_pips = float(os.getenv("TAKE_PROFIT_PIPS", 10)) * pip_size
lot_size = float(os.getenv("LOT_SIZE", 0.1))
reverse_trades = os.getenv("REVERSE_TRADES", "0").strip() == "1"
BOT_MAGIC = 123456
TRADE_INTERVAL = 60
NEWS_CHECK_INTERVAL = 5

# Initialize MetaTrader 5
def initialize_mt5():
    login_settings = {
        "MT5_SERVER": os.getenv("MT5_SERVER", "").strip(),
        "MT5_ACCOUNT": os.getenv("MT5_ACCOUNT", ""),
        "MT5_PASSWORD": os.getenv("MT5_PASSWORD", ""),
    }
    missing_settings = [name for name, value in login_settings.items() if not value.strip()]
    if missing_settings:
        logging.error("Set these values in .env before starting the bot: %s", ", ".join(missing_settings))
        sys.exit(1)

    try:
        account = int(login_settings["MT5_ACCOUNT"])
        if account <= 0:
            raise ValueError
    except ValueError:
        logging.error("MT5_ACCOUNT must be a positive account number.")
        sys.exit(1)

    if not mt5.initialize():
        logging.error("Failed to initialize MetaTrader 5.")
        sys.exit(1)
    if not mt5.login(account, password=login_settings["MT5_PASSWORD"], server=login_settings["MT5_SERVER"]):
        logging.error(f"Failed to log in to MetaTrader 5. Error: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)

# Check if the market is open for the given symbol
def is_market_open(symbol):
    market_info = mt5.symbol_info(symbol)
    if market_info is None:
        logging.error(f"Error retrieving market info for {symbol}. Symbol might not be available.")
        return False
    if market_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        logging.info(f"Market for {symbol} is closed or disabled for trading.")
        return False
    return True

# Get recent market data
def get_data(symbol):
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 50)
        if rates is None:
            logging.error("Failed to retrieve data from MetaTrader 5.")
            return pd.DataFrame()
        data = pd.DataFrame(rates)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        return data
    except Exception as e:
        logging.error(f"Error in get_data: {e}")
        return pd.DataFrame()

# Calculate MACD indicator
def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9):
    data['ema_fast'] = data['close'].ewm(span=fast_period, adjust=False).mean()
    data['ema_slow'] = data['close'].ewm(span=slow_period, adjust=False).mean()
    data['macd'] = data['ema_fast'] - data['ema_slow']
    data['signal'] = data['macd'].ewm(span=signal_period, adjust=False).mean()
    data['hist'] = data['macd'] - data['signal']
    data['macd_cross'] = (data['macd'] > data['signal']) & (data['macd'].shift(1) <= data['signal'].shift(1))
    data['signal_cross'] = (data['macd'] < data['signal']) & (data['macd'].shift(1) >= data['signal'].shift(1))
    return data

# Find support and resistance levels
def find_support_resistance(data):
    recent_highs = data['high'].tail(10)
    recent_lows = data['low'].tail(10)
    resistance_level = recent_highs.max()
    support_level = recent_lows.min()
    return resistance_level, support_level


# Check for trading signals
def check_trade_conditions(data, resistance_level, support_level):
    latest = data.iloc[-1]
    if latest['signal_cross'] and latest['hist'] < 0 and latest['close'] < resistance_level:
        return "sell"
    elif latest['macd_cross'] and latest['hist'] > 0 and latest['close'] > support_level:
        return "buy"
    return None

# Function to calculate indicators for testing
def calculate_indicators(data):
    """
    Calculates and returns key indicators such as MACD, support, and resistance.
    Returns:
        dict: A dictionary with MACD, support, and resistance values.
    """
    data_with_macd = calculate_macd(data)
    resistance_level, support_level = find_support_resistance(data_with_macd)
    return {
        "macd": data_with_macd[['macd', 'signal', 'hist']].tail(1).to_dict('records')[0],
        "support": support_level,
        "resistance": resistance_level
    }


# Place an order with MetaTrader 5
def place_order(direction, tick):
    info = mt5.symbol_info(symbol)
    if info is None:
        logging.error("Could not read trading settings for %s: %s", symbol, mt5.last_error())
        return
    filling_modes = immediate_filling_modes(mt5, info)
    if not filling_modes:
        logging.error("No immediate filling mode available to open %s (execution=%s, filling flags=%s).",
                      symbol, info.trade_exemode, info.filling_mode)
        return

    price = tick.ask if direction == "buy" else tick.bid
    if direction == "sell":
        sl = price + stop_loss_pips  # Stop Loss above sell price
        tp = price - take_profit_pips  # Take Profit below sell price
    else:  # buy
        sl = price - stop_loss_pips  # Stop Loss below buy price
        tp = price + take_profit_pips  # Take Profit above buy price

    if reverse_trades:
        # Keep the original signal's price levels and exchange their roles.
        direction = "sell" if direction == "buy" else "buy"
        price = tick.ask if direction == "buy" else tick.bid
        sl, tp = tp, sl

    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL

    # Place order with SL and TP
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": sl,  # Stop Loss price
        "tp": tp,  # Take Profit price
        "deviation": 20,
        "magic": BOT_MAGIC,
        "comment": "Auto-trading bot",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    
    result = send_with_filling_modes(mt5, request, filling_modes)

    if result is None:
        logging.error("Order failed: %s", mt5.last_error())
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"Order failed: {result.retcode} - {result.comment}")
    else:
        logging.info(f"{direction.capitalize()} order placed at {price} with SL: {sl} and TP: {tp}")


# Display open positions
def show_open_positions():
    positions = mt5.positions_get()
    if positions is None:
        logging.warning("No open positions or failed to retrieve positions.")
        return
    if len(positions) > 0:
        logging.info("Open positions:")
        for pos in positions:
            logging.info(f"Symbol: {pos.symbol}, Type: {'Buy' if pos.type == 0 else 'Sell'}, "
                         f"Volume: {pos.volume}, Open Price: {pos.price_open}, "
                         f"SL: {pos.sl}, TP: {pos.tp}")
    else:
        logging.info("No open positions.")

# Main trading loop
def check_for_trade(calendar):
    if not is_market_open(symbol):
        return
    data = get_data(symbol)
    if data.empty:
        logging.error("Data retrieval failed. Skipping this iteration.")
        return
    data = calculate_macd(data)
    resistance_level, support_level = find_support_resistance(data)
    trade_signal = check_trade_conditions(data, resistance_level, support_level)
    if trade_signal:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error("No current price for %s. %s", symbol, mt5.last_error())
            return
        ready, active = calendar.poll()
        if ready and not active:
            place_order(trade_signal, tick)
    show_open_positions()


def run_trading_bot(calendar):
    next_trade_check = 0
    pending_close = False
    previous_events = ()
    while True:
        ready, active = calendar.poll()
        if active != previous_events:
            for when, source, title in active:
                if (when, source, title) not in previous_events:
                    logging.info("News blackout for %s: %s at %s", source, title,
                                 when.astimezone().isoformat(timespec="minutes"))
            if not active:
                logging.info("News blackout ended.")
            previous_events = active

        clock = monotonic()
        if active or pending_close:
            pending_close = not close_bot_positions(mt5, symbol, BOT_MAGIC)
        elif ready and clock >= next_trade_check:
            next_trade_check = clock + TRADE_INTERVAL
            check_for_trade(calendar)
        sleep(NEWS_CHECK_INTERVAL)


def main():
    try:
        before_minutes = int(os.getenv("NEWS_BEFORE_MINUTES", "30"))
        after_minutes = int(os.getenv("NEWS_AFTER_MINUTES", "30"))
        if before_minutes <= 0 or after_minutes < 0:
            raise ValueError
    except ValueError:
        logging.error("Use whole minutes: NEWS_BEFORE_MINUTES must be positive and NEWS_AFTER_MINUTES nonnegative.")
        sys.exit(1)

    if not symbol:
        logging.error("Set SYMBOL in .env before starting the bot.")
        sys.exit(1)

    initialize_mt5()
    try:
        with ThreadPoolExecutor(max_workers=len(SOURCES)) as executor:
            calendar = EconomicCalendar(executor, before_minutes, after_minutes)
            run_trading_bot(calendar)
    except KeyboardInterrupt:
        logging.info("Trading bot stopped.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
