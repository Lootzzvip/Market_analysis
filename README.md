# 🤖 24/7 Smart Money Concepts Trading Bot

[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-24%2F7%20Trading-blue)](https://github.com/features/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent, fully automated trading bot using **Smart Money Concepts (SMC)** and **Machine Learning** to trade Bitcoin 24/7 with automatic learning from wins and losses.

## ✨ Features

### 🎯 Smart Money Concepts
- **Fair Value Gaps (FVG)** detection
- **Break of Structure (BOS)** identification
- **Order Blocks** analysis
- **Multi-timeframe confluence** scoring
- **Higher timeframe bias** filtering

### 🤖 Machine Learning
- **Random Forest** model for FVG prediction
- **Automatic learning** from closed trades
- **Adaptive thresholds** based on performance
- **Pattern recognition** from historical data

### 🛡️ Advanced Safety Filters
- ✅ **HTF Bias Filter** - Only trade with higher timeframe trend
- ✅ **ADX Trend Filter** - Avoid ranging/choppy markets (requires ADX > 20)
- ✅ **Volume Filter** - Require above-average volume confirmation
- ✅ **RSI Extremes** - Avoid overbought (>70) / oversold (<30) zones
- ✅ **Win Rate Circuit Breaker** - Auto-pause if win rate drops below threshold
- ✅ **Confluence Validation** - Strict scoring requirements

### 📊 Risk Management
- **1:3 Risk-Reward ratio** (configurable 1:2 to 1:5)
- **Position sizing** based on 2% risk per trade
- **Max open trades** limit (4 trades default)
- **Trade cooldowns** to avoid overtrading
- **Stop loss & take profit** on every trade

### 🚀 Deployment Options
1. **GitHub Actions** (Free, runs every 5 minutes)
2. **Cloud Server** (AWS, DigitalOcean - 24/7 continuous)
3. **Local PC** (Your computer)

---

## 📸 Screenshots

### Streamlit Dashboard
- Real-time price charts with indicators
- Multi-timeframe scanning
- Active trades monitoring
- ML performance analytics
- Trade history with win/loss breakdown

### Headless Bot Logs
```
🔍 STARTING SCAN CYCLE - 2026-03-08 14:30:00
📈 HTF Bias: 🟢 BULLISH
📊 Overall Stats: 15 trades | Win Rate: 46.7% | P&L: $487.50
🎯 15m: BUY SIGNAL - Bullish FVG (72 conf) + BOS + RSI 54.2 + ADX 28.5 + HTF✅
✅ 15m: TRADE #16 EXECUTED!
   Entry: $67,450.00 | SL: $67,150.00 | TP: $68,350.00
✨ Scan cycle complete - 1 new trades executed
```

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/trading-bot.git
cd trading-bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Choose Your Mode

#### Option A: Interactive Dashboard (with UI)
```bash
streamlit run app.py
```
Open http://localhost:8501 in your browser

#### Option B: Headless Bot (24/7 automated)
```bash
python trading_bot_headless.py
```

#### Option C: GitHub Actions (Free Cloud)
- Push code to GitHub
- Enable Actions in repository settings
- Bot runs automatically every 5 minutes!

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

---

## ⚙️ Configuration

Edit `CONFIG` in `trading_bot_headless.py`:

```python
CONFIG = {
    'scan_interval_seconds': 300,  # Scan every 5 minutes
    'timeframes_to_scan': ['1h', '15m', '5m', '1m'],
    'min_confluence_threshold': 60,  # Higher = more selective
    'risk_reward_ratio': 3,  # 1:3 risk-reward
    
    # Safety filters (True = enabled)
    'enable_htf_filter': True,
    'enable_adx_filter': True,
    'enable_volume_filter': True,
    'min_win_rate_threshold': 35,  # Pause if win rate drops below this
}
```

---

## 📊 How It Works

### 1. **Multi-Timeframe Scanning**
Every 5 minutes, the bot scans:
- 1h, 15m, 5m, 1m timeframes (turbo mode)
- Calculates HTF bias from 1d and 4h charts
- Identifies FVGs, BOS, Order Blocks

### 2. **Signal Generation**
Applies 7 safety filters:
1. ✅ Win rate check (pause if too low)
2. ✅ FVG existence
3. ✅ Confluence threshold (60+ points)
4. ✅ HTF bias alignment
5. ✅ ADX trend strength (>20)
6. ✅ Volume confirmation (>80% average)
7. ✅ RSI extremes (30-70 range)

### 3. **Trade Execution**
If all filters pass:
- Calculate entry/SL/TP prices
- Check for duplicate setups
- Execute trade with proper position sizing
- Log to database

### 4. **Trade Management**
- Monitor open trades every cycle
- Check if TP or SL was hit (using candle wicks)
- Close trades automatically
- Update P&L and statistics

### 5. **Machine Learning**
- Learn from closed trades
- Adjust model weights
- Improve future predictions
- Store patterns in database

---

## 📈 Performance Metrics

After running for some time, check performance:

```bash
# View logs
tail -n 100 trading_bot.log

# Query database
sqlite3 trades.db "SELECT * FROM trades WHERE result IS NOT NULL ORDER BY exit_time DESC LIMIT 20;"

# Get win rate
sqlite3 trades.db "SELECT COUNT(*) as total, SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END)*100.0/COUNT(*) as win_rate FROM trades WHERE result IS NOT NULL;"
```

---

## 📂 Project Structure

```
├── app.py                          # Streamlit dashboard (interactive UI)
├── trading_bot_headless.py         # 24/7 automated bot (no UI)
├── trading_bot_single_cycle.py     # Single scan cycle (for GitHub Actions)
├── requirements.txt                # Python dependencies
├── trades.db                       # SQLite database (auto-created)
├── trading_bot.log                 # Log file (auto-created)
├── .github/
│   └── workflows/
│       └── trading-bot.yml         # GitHub Actions workflow
├── DEPLOYMENT_GUIDE.md             # Detailed deployment instructions
└── README.md                       # This file
```

---

## 🛡️ Safety & Disclaimers

⚠️ **IMPORTANT:**
- This is for **educational and testing purposes only**
- **Not financial advice** - crypto trading is high risk
- **Test thoroughly** before using real money
- Bot uses **simulated trading** by default (paper trading)
- Always **monitor logs** regularly
- Set **stop losses** on all trades
- Never risk more than you can afford to lose

---

## 🔧 Troubleshooting

### No trades being executed?
- Check logs: `tail -f trading_bot.log`
- Lower confluence threshold to 50-55
- Disable a safety filter temporarily
- Verify Binance API is accessible

### Bot stopped running?
```bash
# Check status (if using systemd)
sudo systemctl status trading-bot

# Restart
sudo systemctl restart trading-bot
```

### Want to reset database?
```bash
# Backup first
cp trades.db trades.db.backup

# Clear all trades
python
>>> from app import TradeMemory
>>> tm = TradeMemory()
>>> tm.clear_all_trades()
```

---

## 📚 Resources

- [Smart Money Concepts Guide](https://www.tradingview.com/scripts/smartmoneyconcept/)
- [Binance API Documentation](https://binance-docs.github.io/apidocs/)
- [CCXT Library](https://github.com/ccxt/ccxt)
- [Streamlit Documentation](https://docs.streamlit.io/)

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## ⭐ Star History

If this project helps you, please consider giving it a ⭐!

---

## 📞 Support

For issues or questions:
- Open an issue on GitHub
- Check `trading_bot.log` for error messages
- Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

**Happy Trading! 🚀📈**
