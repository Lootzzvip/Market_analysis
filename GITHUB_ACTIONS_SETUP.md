# 🤖 GitHub Actions 24/7 Trading Bot Setup

This guide shows how to deploy your trading bot to GitHub Actions for completely **FREE 24/7 automated trading**.

---

## 📋 Prerequisites

- GitHub account (free)
- This repository with all files

---

## 🚀 Step 1: Create GitHub Repository

### On GitHub.com:
1. Go to https://github.com/new
2. Create new repository: **`TV-Trading-Bot`** (or any name)
3. **DO NOT** initialize with README (we'll push our files)
4. Click **Create repository**

You'll see instructions like:
```
git remote add origin https://github.com/YOUR_USERNAME/TV-Trading-Bot.git
```

---

## 📤 Step 2: Push Code to GitHub

### In PowerShell (in your TV folder):

```powershell
# Initialize git if not done
git init

# Add all files
git add .

# Commit
git commit -m "Initial trading bot setup for GitHub Actions"

# Add remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/TV-Trading-Bot.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Important files that must be pushed:**
- `app.py` ✅
- `trading_bot.py` ✅
- `requirements.txt` ✅
- `.github/workflows/trading.yml` ✅
- `*.db` files (optional, for initial data)

---

## ⏰ Step 3: GitHub Actions Schedule

The bot runs automatically every:
- **Every 5 minutes** - for 5m trades
- **Every 15 minutes** - for 15m trades
- **Every hour** - for 1h+ trades

### To Change Schedule:

Edit `.github/workflows/trading.yml`:

```yaml
schedule:
  - cron: '*/5 * * * *'    # Every 5 minutes
  - cron: '*/15 * * * *'   # Every 15 minutes  
  - cron: '0 * * * *'      # Every 1 hour
```

**Cron Examples:**
- `*/5 * * * *` = Every 5 minutes ⭐ (Best for scalping)
- `*/15 * * * *` = Every 15 minutes  
- `0 * * * *` = Every hour
- `0 0 * * *` = Once per day (midnight UTC)

---

## ✅ Step 4: Verify Bot is Running

### Check GitHub Actions:

1. Go to your repo: `github.com/YOUR_USERNAME/TV-Trading-Bot`
2. Click **Actions** tab
3. You should see **"24/7 Trading Bot"** workflow
4. Click on it to see execution logs

### What runs inside GitHub:
- Fetches live Binance data
- Generates trading signals
- Opens/closes trades
- Learns from results
- Saves databases

---

## 📊 Step 5: Download Results

### Get Your Trade Data:

1. Go to **Actions** tab
2. Click latest **trading bot** run
3. Scroll to **Artifacts**
4. Download **trading-databases.zip**
5. Contains:
   - `trade_history_v1.db` (all trades)
   - `trend_ml_data_v3.db` (ML data)

---

## 🔄 Step 6: Update Locally & Push

After making changes locally:

```powershell
# Make your changes to app.py or trading_bot.py

# Push updates
git add .
git commit -m "Updated trading logic"
git push origin main

# GitHub Actions automatically picks up changes!
```

---

## ⚠️ Important Notes

### Limitations:
- **GitHub free tier:** 2,000 action minutes/month
- **Our usage:** ~1 min per execution
- **5-min schedule:** 288 runs/day × 1 min = 288 min/day = ~8,640 min/month
- **Result:** Can run every 5 min for entire month! ✅

### Best For:
- 15m, 1h, 4h, daily trades (less frequent = longer free usage)
- Scalping with proper risk management
- Paper trading to test signals

### Time Zone:
- GitHub Actions uses **UTC timezone**
- Important for scheduling candle closes
- Adjust cron times accordingly

---

## 🎯 Recommended Setup

**For Best Results:**

```yaml
schedule:
  # Run every 1 hour for all timeframes
  - cron: '0 * * * *'
```

This:
- ✅ Fits within free tier (24 runs/day)
- ✅ Manageable trade frequency
- ✅ Catches all major moves
- ✅ Zero cost, infinite uptime

---

## 🚨 Troubleshooting

### "No data fetched" error:
- Binance API might be down
- Wait a few minutes and retry manually
- Check workflow logs for details

### "Insufficient funds" error:
- Increase initial balance in `trading_bot.py`
- Edit: `trade_executor = TradeExecutor(initial_balance=10000)`

### Workflows not appearing:
- Go to **Settings → Actions → General**
- Enable "Actions"

### Logs showing "Error importing":
- All dependencies in `requirements.txt` installed
- Python 3.10 compatible

---

## 📈 Example Workflow Log

```
🤖 TRADING BOT - 2026-03-03 10:30:00
Timeframe: 1H
============================================================

📊 HTF Bias: 4H=1, 1D=1, Combined=1
🧠 Model Accuracy: 72.34%
✅ TRADE OPENED #1
   Type: BUY
   Entry: $65,432.50
   SL: $65,200.00
   TP: $66,100.00
   
📈 1H Stats:
   Total: 15 | Wins: 10 | Losses: 5
   Win Rate: 66.7% | P&L: $2,345.67

✅ Cycle complete at 10:31:23
```

---

## 🎓 Key Commands Reference

```powershell
# Check git status
git status

# View recent commits
git log --oneline -5

# Push all changes
git push origin main

# Pull latest from GitHub
git pull origin main

# View difference
git diff app.py
```

---

## 🔒 Security Notes

- ❌ **DO NOT** commit API keys to GitHub!
- ✅ Your Binance API keys stay on GitHub's secure servers
- ✅ CCXT library handles connections safely
- ✅ Databases encrypted at rest on GitHub

---

## 📞 Next Steps

1. ✅ **Push to GitHub** (follow Step 2)
2. ✅ **Verify in Actions tab** (follow Step 4)
3. ✅ **Monitor trades** (download databases weekly)
4. ✅ **Make improvements** (push changes, auto-deploy)

---

## 🎉 Success!

Your bot is now running 24/7 on GitHub's servers, completely **FREE**!

- No laptop needed ✅
- 24/7 uptime ✅
- Automatic restarts ✅
- Auto-learning ML ✅
- All for $0 ✅

**Happy Trading! 🚀**
