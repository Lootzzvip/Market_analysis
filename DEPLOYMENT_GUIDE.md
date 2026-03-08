# 🤖 24/7 Trading Bot Deployment Guide

## Overview

This trading bot can run 24/7 in three modes:
1. **GitHub Actions** (Free, Recommended for testing)
2. **Cloud Server** (AWS, DigitalOcean, etc.)
3. **Local PC** (Your computer)

---

## ✅ Option 1: GitHub Actions (FREE)

### Advantages:
- ✅ **Completely free**
- ✅ No server management
- ✅ Automatic database persistence
- ✅ Built-in logging

### Limitations:
- ⚠️ Runs every 5 minutes (not continuous)
- ⚠️ 6 hour workflow timeout per run
- ⚠️ Public repo required for free tier

### Setup Steps:

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

2. **Enable GitHub Actions**
   - Go to your repository on GitHub
   - Click "Actions" tab
   - Enable workflows

3. **The bot will automatically run every 5 minutes!**
   - Check "Actions" tab to see runs
   - Download logs from "Artifacts" section

4. **Manual trigger** (optional)
   - Go to Actions → "24/7 Trading Bot"
   - Click "Run workflow"

### View Results:
- **Logs:** Actions → Latest run → Download "trading-logs" artifact
- **Database:** Persisted between runs automatically

---

## ✅ Option 2: Cloud Server (24/7 Continuous)

### Recommended Providers:
- **AWS EC2** (t2.micro = $8-10/month)
- **DigitalOcean Droplet** ($4-6/month)
- **Google Cloud** (Free tier available)
- **Heroku** (Free tier but less reliable)

### Setup on Ubuntu Server:

1. **SSH into your server**
   ```bash
   ssh user@your-server-ip
   ```

2. **Install Python**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip git -y
   ```

3. **Clone your repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
   cd YOUR_REPO
   ```

4. **Install dependencies**
   ```bash
   pip3 install -r requirements.txt
   ```

5. **Run bot in background (Method 1: tmux)**
   ```bash
   # Install tmux
   sudo apt install tmux -y
   
   # Start new session
   tmux new -s trading_bot
   
   # Run bot
   python3 trading_bot_headless.py
   
   # Detach: Press Ctrl+B, then D
   # Reattach later: tmux attach -t trading_bot
   ```

6. **Run bot in background (Method 2: systemd service)**
   ```bash
   sudo nano /etc/systemd/system/trading-bot.service
   ```
   
   Paste this:
   ```ini
   [Unit]
   Description=24/7 Trading Bot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/YOUR_REPO
   ExecStart=/usr/bin/python3 /home/ubuntu/YOUR_REPO/trading_bot_headless.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
   
   Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable trading-bot
   sudo systemctl start trading-bot
   
   # Check status
   sudo systemctl status trading-bot
   
   # View logs
   sudo journalctl -u trading-bot -f
   ```

---

## ✅ Option 3: Local PC (Windows)

### Setup:

1. **Open PowerShell in project folder**

2. **Run continuously**
   ```powershell
   python trading_bot_headless.py
   ```

3. **Run in background (PowerShell)**
   ```powershell
   Start-Process python -ArgumentList "trading_bot_headless.py" -WindowStyle Hidden
   ```

4. **Keep running on startup**
   - Press `Win + R`
   - Type `shell:startup`
   - Create a batch file `start_bot.bat`:
     ```batch
     @echo off
     cd C:\Users\Sharath\Desktop\TV
     python trading_bot_headless.py
     ```
   - Copy `start_bot.bat` to startup folder

---

## 📊 Monitoring Your Bot

### View Logs:
```bash
# Real-time logs
tail -f trading_bot.log

# Last 100 lines
tail -n 100 trading_bot.log

# Search for wins
grep "WON" trading_bot.log

# Search for losses
grep "LOST" trading_bot.log
```

### Check Database:
```bash
# Install sqlite3
sudo apt install sqlite3

# Query trades
sqlite3 trades.db "SELECT * FROM trades ORDER BY entry_time DESC LIMIT 10;"

# Get stats
sqlite3 trades.db "SELECT COUNT(*) as total, SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins FROM trades WHERE result IS NOT NULL;"
```

---

## ⚙️ Configuration

Edit `CONFIG` in `trading_bot_headless.py`:

```python
CONFIG = {
    'scan_interval_seconds': 300,  # Scan every 5 minutes
    'timeframes_to_scan': ['1h', '15m', '5m', '1m'],
    'min_confluence_threshold': 60,  # Increase for fewer, better trades
    'risk_reward_ratio': 3,  # 1:3 risk-reward
    
    # Safety filters
    'enable_htf_filter': True,  # Only trade with HTF trend
    'enable_adx_filter': True,  # Only trade in trending markets
    'enable_volume_filter': True,  # Require volume confirmation
    'min_win_rate_threshold': 35,  # Pause if win rate drops below 35%
    
    # Trade limits
    'max_open_trades': 4,
    'max_trades_per_timeframe': 1,
}
```

---

## 🛡️ Safety Features

The bot automatically:
- ✅ **Pauses trading** if win rate drops below threshold
- ✅ **Logs all trades** with timestamps
- ✅ **Persists data** in SQLite database
- ✅ **Learns from mistakes** (via ML model)
- ✅ **Limits risk** (max open trades, position sizing)
- ✅ **Filters bad setups** (HTF bias, ADX, volume)

---

## 🔧 Troubleshooting

### Bot stops unexpectedly:
```bash
# Check logs
tail -n 50 trading_bot.log

# Restart service (if using systemd)
sudo systemctl restart trading-bot
```

### No trades being taken:
- Check logs for rejection reasons
- Lower `min_confluence_threshold` to 50-55
- Disable some safety filters temporarily
- Check if win rate threshold was hit (paused trading)

### Database errors:
```bash
# Backup database
cp trades.db trades.db.backup

# Clear database (start fresh)
rm trades.db
```

### API rate limits:
- Binance allows 1200 requests/minute
- Bot is designed to stay well below this
- If hitting limits, increase `scan_interval_seconds`

---

## 📈 Expected Performance

With all safety filters enabled:
- **Signals:** 1-5 per day (very selective)
- **Win Rate:** Target 40-50%+
- **Risk:Reward:** 1:3 (1 win covers 3 losses)
- **Drawdown:** Should pause if win rate drops below 35%

---

## 🚨 Important Reminders

1. **This is for testing/education** - Not financial advice
2. **Use paper trading** first (bot simulates trades by default)
3. **Monitor logs** regularly for first few days
4. **Adjust settings** based on performance
5. **Keep backups** of trades.db database

---

## 📞 Support

If bot encounters errors:
1. Check `trading_bot.log` for error messages
2. Verify Binance API is accessible
3. Ensure database has write permissions
4. Check internet connection stability

Good luck with your automated trading! 🚀
