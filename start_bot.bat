@echo off
REM 24/7 Trading Bot Startup Script for Windows

echo ==================================================
echo 🤖 Starting 24/7 Trading Bot
echo ==================================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed!
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python found

REM Install dependencies
echo 📦 Checking dependencies...
pip install -r requirements.txt

REM Create backup of database if it exists
if exist trades.db (
    set BACKUP_NAME=trades.db.backup.%date:~-4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    copy trades.db %BACKUP_NAME%
    echo ✅ Database backed up
)

REM Start the bot
echo 🚀 Starting bot...
echo 📝 Logs will be written to: trading_bot.log
echo ⏹️  Press Ctrl+C to stop
echo ==================================================
echo.

python trading_bot_headless.py

pause
