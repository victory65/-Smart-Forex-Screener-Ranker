# -Smart-Forex-Screener-Ranker
Scan the entire FX board in seconds, then tell you which three pairs are the hottest and why
A lightweight, dependency-light Python utility that:
Connects to MetaTrader 5
Pulls the last 14 bars on M30 and H2 for 30+ FX pairs
Calculates ATR, price-change %, and volume-based reversal signals
Ranks every currency by aggregated volatility
Spits out the top-3 non-clustered pairs to trade right now
Logs actionable “smart-money” alerts every 30 minutes

also make sure to have the mt5 terminal installed and make sure you login to your account(can be demo or real)

| Feature                  | How it works                              |
| ------------------------ | ----------------------------------------- |
| **Volatility rank**      | ATR and % change normalized & weighted    |
| **Smart-money detector** | Volume spike + reversal candle            |
| **Currency clustering**  | Avoids double-exposure on same base/quote |
| **Multi-timeframe**      | Runs on M30 and H2 simultaneously         |
| **Ultra-light**          | No heavy ML, pure pandas & numpy          |
| **Headless**             | Runs in a terminal or on a cheap VPS      |


Quick Start
pip install MetaTrader5 pandas numpy
python scanner.py
Output (every 30 min):

Best pair to trade (H2): USDJPYm – Score 0.82, ATR 0.00123, Price ↑1.7 %
Smart money activity: AUDCADm – Bullish reversal with volume spike

Why it exists
I wanted a zero-config companion that sits next to my main EA and keeps me focused on the three pairs with the most juice—without staring at 30 charts.
