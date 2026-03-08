#!/bin/bash

# 24/7 Trading Bot Startup Script

echo "=================================================="
echo "🤖 Starting 24/7 Trading Bot"
echo "=================================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    echo "Install it with: sudo apt install python3 python3-pip"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if dependencies are installed
if ! python3 -c "import ccxt" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
fi

echo "✅ Dependencies installed"

# Create backup of database if it exists
if [ -f "trades.db" ]; then
    BACKUP_NAME="trades.db.backup.$(date +%Y%m%d_%H%M%S)"
    cp trades.db "$BACKUP_NAME"
    echo "✅ Database backed up to $BACKUP_NAME"
fi

# Start the bot
echo "🚀 Starting bot..."
echo "📝 Logs will be written to: trading_bot.log"
echo "⏹️  Press Ctrl+C to stop"
echo "=================================================="
echo ""

python3 trading_bot_headless.py
