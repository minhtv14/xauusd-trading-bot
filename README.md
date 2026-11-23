# XAU/USD Trading Bot

This is an automated bot designed to trade the **Gold (XAU) to US Dollar (USD)** currency pair on the MetaTrader 5 (MT5) platform. It uses a **MACD-based trading strategy** combined with **price action** to generate buy and sell signals.

---

## ⚠️ VERY IMPORTANT NOTES

> This software is for educational and testing purposes only. Do not risk money which you are afraid to lose. USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME NO RESPONSIBILITY FOR YOUR TRADING RESULTS.
>Always start by running a trading bot on demo accounts and do not engage money before you understand how it works and what profit/loss you should expect.
> The current setup includes predefined risk management rules (e.g., **Stop Loss: 15 pips**). Adjust these parameters to match your personal risk management strategy.
> Better results are shown during the London session.

---

## 🌟 Features

- **MACD Strategy:**  
  The bot uses the **MACD (Moving Average Convergence Divergence)** indicator to identify buy and sell signals based on market momentum.

- **Price Action:**  
  Dynamic calculation of **support** and **resistance levels** using the last 10 bars to optimize trade entry/exit points.

- **Risk Management:**  
  Predefined **Stop Loss** (15 pips) and **Take Profit** (10 pips) for automated risk management.

- **Real-Time Trading:**  
  Executes trades in real-time using the **MetaTrader 5 API**.

---

## 📈 Trading Strategy

### Buy Signal Setup:
- When the MACD line crosses above the signal line **then** the price crosses above the last resistance level in the 1 min time frame.

### Sell Signal Setup:
- When the MACD line crosses below the signal line **then** the price crosses below the last support level in the 1 min time frame.

### Risk Management:
- **Stop Loss:** Set at **15 pips**.
- **Take Profit:** Set at **10 pips**.

---

## ⚙️ Installation

### 1. Clone the Repository

First, clone this repository to your local machine:
git clone https://github.com/3aLaee/xauusd-trading-bot.git

### 2. Install Dependencies

pip install -r requirements.txt

### 3. Set Up the `.env` File

Create a `.env` file to store data such as your MetaTrader 5 credentials and trading parameters. Here's an example of what the `.env` file should look like:

```dotenv
MT5_ACCOUNT=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_server_name
SYMBOL=XAUUSD
PIP_SIZE=0.10
STOP_LOSS_PIPS=15
TAKE_PROFIT_PIPS=10
REVERSE_TRADES=0
LOT_SIZE=0.1
NEWS_BEFORE_MINUTES=30
NEWS_AFTER_MINUTES=30
```

Use the exact server name shown for your account in the MetaTrader 5 terminal. Set `SYMBOL` to the name your broker uses for XAU/USD.

Set `REVERSE_TRADES=1` to turn BUY signals into SELL orders and SELL signals into BUY orders. The bot uses the original take-profit price as the new stop loss and the original stop-loss price as the new take profit. Restart the bot to apply the setting to new orders.

### U.S. economic releases

The bot loads the official [BLS iCalendar](https://www.bls.gov/help/hlpiCAL.htm), [BEA release calendar](https://www.bea.gov/news/schedule/icalendar), and [Federal Reserve monthly calendar](https://www.federalreserve.gov/newsevents/calendar.htm). It uses releases with published times, including FOMC statements, press conferences and minutes, the Beige Book, and Fed statistical releases. It accounts for changes between standard time and daylight saving time in New York. Calendar times in the log use the computer's local time zone.

- By default, the bot blocks new orders from 30 minutes before each release until 30 minutes after it. Adjust `NEWS_BEFORE_MINUTES` and `NEWS_AFTER_MINUTES` in `.env`.
- At the start of the blackout, the bot attempts to close its positions for `SYMBOL` and retries about every five seconds while it is running. If MT5 cannot confirm closure, the bot keeps new entries paused. On netting accounts, positions that combine bot and other trades require manual handling.
- The bot loads the schedules at startup and refreshes them once each day at local midnight. If a source fails, new orders pause while the bot retries that source every minute. Previously loaded release windows still trigger close attempts.
- If BLS denies the automated download, download the [official BLS calendar file](https://www.bls.gov/schedule/news_release/bls.ics) and set `BLS_CALENDAR_FILE=bls.ics` in `.env` if you save it in the project directory. When loading the fallback file, the bot checks that it was updated within the last 24 hours and covers the required dates.

## 🛠 Contributing

I welcome contributions! To contribute to this project, follow these steps:

1. **Fork the repository** and clone it to your local machine.
2. **Create a new branch** for your feature:
   git checkout -b feature-name
3. Make your changes to the code.
4. Commit your changes with a descriptive message:
  git commit -m "Description of the changes"
5- Push to your fork:
  git push origin feature-name
6. Create a pull request to merge your changes into the main branch.

We ask that you ensure your code is clean, well-documented, and thoroughly tested before submitting a pull request.

## 📝 License
This project is licensed under the ![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
. For more details, please check the LICENSE file.










