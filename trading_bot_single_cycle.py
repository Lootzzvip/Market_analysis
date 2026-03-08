"""
Single-Cycle Trading Bot for GitHub Actions
Runs one scan cycle and exits (GitHub Actions will re-run every 5 minutes)
"""

import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import the headless bot
try:
    from trading_bot_headless import HeadlessTradingBot, CONFIG
except ImportError as e:
    logger.error(f"Failed to import: {e}")
    sys.exit(1)

if __name__ == "__main__":
    logger.info(f"\n{'='*80}")
    logger.info(f"🤖 SINGLE CYCLE RUN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*80}")
    
    try:
        bot = HeadlessTradingBot(CONFIG)
        bot.run_scan_cycle()
        logger.info("✅ Cycle completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Cycle failed: {e}")
        sys.exit(1)
