# 🚀 QUICK START - Upload to GitHub & Run 24/7

## Step 1: Upload to GitHub (5 minutes)

1. **Create a new GitHub repository**
   - Go to https://github.com/new
   - Name it: `trading-bot`
   - Make it **PUBLIC** (required for free GitHub Actions)
   - Don't initialize with README
   - Click "Create repository"

2. **Upload your code**
   
   Open PowerShell in `C:\Users\Sharath\Desktop\TV\` and run:
   
   ```powershell
   # Initialize git
   git init
   
   # Add all files
   git add .
   
   # Commit
   git commit -m "Initial commit - 24/7 Trading Bot"
   
   # Add GitHub as remote (replace YOUR_USERNAME and trading-bot with your details)
   git remote add origin https://github.com/YOUR_USERNAME/trading-bot.git
   
   # Push to GitHub
   git branch -M main
   git push -u origin main
   ```

3. **Enable GitHub Actions**
   - Go to your repository on GitHub
   - Click "Actions" tab
   - Click "I understand my workflows, go ahead and enable them"

## Step 2: Bot Runs Automatically! ✅

That's it! The bot will now:
- ✅ Run every 5 minutes automatically
- ✅ Scan for trade opportunities
- ✅ Execute trades when conditions met
- ✅ Update open trades
- ✅ Learn from wins/losses
- ✅ Persist data between runs

## Step 3: Monitor Your Bot

### View Logs:
1. Go to your repo → "Actions" tab
2. Click on latest workflow run
3. Click on "trade" job
4. Expand "Run trading bot (single cycle)"
5. See live logs!

### Download Full Logs:
1. Go to completed workflow run
2. Scroll to bottom → "Artifacts"
3. Download "trading-logs"
4. Unzip and open `trading_bot.log`

### Check Performance:
Look for these in logs:
```
✅ Trade #1 WON! P&L: $450.00
❌ Trade #2 LOST! P&L: -$150.00
📊 Overall Stats: 10 trades | Win Rate: 60.0% | P&L: $1,245.50
```

## Step 4: Adjust Settings (Optional)

Edit `trading_bot_headless.py` on line 22-40:

```python
CONFIG = {
    'min_confluence_threshold': 60,  # Higher = fewer, better trades (try 65-70)
    'risk_reward_ratio': 3,          # Higher = more profit per win (try 4-5)
    'enable_htf_filter': True,       # Set False if no trades happening
    'enable_adx_filter': True,       # Set False if market is ranging
    'min_win_rate_threshold': 35,    # Lower to 30 if bot pauses too early
}
```

Commit and push changes:
```powershell
git add .
git commit -m "Adjust settings"
git push
```

## Step 5: Manual Run (Test Now)

Don't want to wait 5 minutes? Trigger manually:

1. Go to repo → "Actions" tab
2. Click "24/7 Trading Bot" workflow
3. Click "Run workflow" dropdown
4. Click green "Run workflow" button

Bot runs immediately!

---

## 🛡️ Safety Features Enabled

Your bot has these protections:
- ✅ Only trades with HTF trend alignment
- ✅ Requires trending market (ADX > 20)
- ✅ Needs volume confirmation
- ✅ Avoids overbought/oversold (RSI 30-70)
- ✅ Auto-pauses if win rate < 35%
- ✅ Max 4 open trades
- ✅ 1:3 risk-reward ratio

---

## 📊 What to Expect

### First 24 Hours:
- **Signals:** 2-8 trades (depends on market)
- **Win Rate:** Unknown (need 10+ trades to judge)
- **Selectivity:** Very picky due to safety filters

### After 1 Week:
- **Should have:** 10-30 trades
- **Target win rate:** 40-50%
- **If win rate < 35%:** Bot auto-pauses for review

### Long Term:
- Bot learns from mistakes
- ML model improves
- Better entries over time

---

## 🔧 Troubleshooting

### No trades happening?
**Check logs for reasons:**
- "Confluence too low" → Lower threshold to 55
- "HTF bias mismatch" → Disable HTF filter
- "ADX too weak" → Disable ADX filter
- "Low volume" → Disable volume filter

### Bot paused?
If you see: `⛔ Trading paused - Win rate XX% < 35%`

**Options:**
1. Review why trades lost (check logs)
2. Adjust confluence threshold
3. Disable some filters
4. Lower `min_win_rate_threshold` to 30

### Want to reset and start fresh?
In Streamlit dashboard:
1. Go to sidebar → "🗑️ Reset Database"
2. Click "🗑️ Clear All Trades"
3. Confirm

---

## 📞 Need Help?

1. Check `DEPLOYMENT_GUIDE.md` for detailed instructions
2. Review logs in GitHub Actions artifacts
3. Look at `trading_bot.log` for error messages

---

## 🎉 You're Done!

Your bot is now running 24/7 in the cloud, completely free! Check back in a few hours to see your first trades.

**Happy automated trading! 🚀📈**
