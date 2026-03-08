"""
24/7 Headless Trading Bot - Runs without UI
Automatically scans, trades, and learns from results
"""

import ccxt
import pandas as pd
import numpy as np
import sqlite3
import time
import logging
from datetime import datetime, timedelta
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - Adjust these settings
# ============================================================================

CONFIG = {
    'symbol': 'BTC/USDT',
    'initial_balance': 10000,
    'scan_interval_seconds': 300,  # Scan every 5 minutes
    'timeframes_to_scan': ['1h', '15m', '5m', '1m'],  # Turbo mode timeframes
    'min_confluence_threshold': 60,
    'risk_reward_ratio': 3,
    
    # Safety filters
    'enable_htf_filter': True,
    'enable_adx_filter': True,
    'enable_volume_filter': True,
    'min_win_rate_threshold': 35,
    
    # Trade limits
    'max_open_trades': 4,
    'max_trades_per_timeframe': 1,
    
    # Database
    'db_path': 'trades.db'
}

# ============================================================================
# Import necessary classes from main app
# ============================================================================

# Import from app.py (make sure app.py is in same directory)
try:
    from app import (
        BinanceDataFetcher,
        SMCIndicators,
        TradeMemory,
        TradeExecutor
    )
    logger.info("✅ Successfully imported trading classes")
except ImportError as e:
    logger.error(f"❌ Failed to import from app.py: {e}")
    logger.error("Make sure app.py is in the same directory")
    sys.exit(1)

# ============================================================================
# HEADLESS BOT CLASS
# ============================================================================

class HeadlessTradingBot:
    def __init__(self, config):
        self.config = config
        self.fetcher = BinanceDataFetcher()
        self.trade_executor = TradeExecutor(initial_balance=config['initial_balance'])
        self.last_scan_time = {}
        self.running = True
        
        logger.info("=" * 80)
        logger.info("🤖 HEADLESS TRADING BOT INITIALIZED")
        logger.info(f"Symbol: {config['symbol']}")
        logger.info(f"Timeframes: {', '.join(config['timeframes_to_scan'])}")
        logger.info(f"Scan Interval: {config['scan_interval_seconds']}s")
        logger.info(f"Safety Filters: HTF={config['enable_htf_filter']}, ADX={config['enable_adx_filter']}, Volume={config['enable_volume_filter']}")
        logger.info("=" * 80)
    
    def compute_htf_bias(self, df_htf):
        """Calculate higher timeframe bias"""
        if df_htf is None or df_htf.empty or len(df_htf) < 60:
            return 0
        ema_fast = df_htf['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema_slow = df_htf['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        last_close = df_htf['close'].iloc[-1]
        if ema_fast > ema_slow and last_close > ema_slow:
            return 1
        if ema_fast < ema_slow and last_close < ema_slow:
            return -1
        return 0
    
    def get_combined_htf_bias(self):
        """Get combined bias from higher timeframes"""
        try:
            df_1d = self.fetcher.fetch_historical_data(timeframe='1d', limit=100)
            df_4h = self.fetcher.fetch_historical_data(timeframe='4h', limit=100)
            
            bias_1d = self.compute_htf_bias(df_1d)
            bias_4h = self.compute_htf_bias(df_4h)
            
            # Weighted combination
            combined = (bias_1d * 0.6) + (bias_4h * 0.4)
            
            if combined > 0.3:
                return 1  # Bullish
            elif combined < -0.3:
                return -1  # Bearish
            return 0  # Neutral
        except Exception as e:
            logger.warning(f"⚠️ Failed to compute HTF bias: {e}")
            return 0
    
    def generate_signal_with_filters(self, df, timeframe, htf_bias, confluenceThreshold):
        """Generate signal with safety filters applied (standalone, no Streamlit dependency)"""
        if len(df) < 5:
            return {'type': 'NONE', 'reason': 'Insufficient data'}
        
        latest = df.iloc[-1]
        
        # FILTER 1: Win Rate Circuit Breaker
        stats = self.trade_executor.trade_memory.get_overall_stats()
        if stats['total_trades'] >= 10:
            recent_win_rate = stats['win_rate']
            min_win_rate = self.config['min_win_rate_threshold']
            if recent_win_rate < min_win_rate:
                return {
                    'type': 'NONE',
                    'reason': f'⛔ Trading paused - Win rate {recent_win_rate:.1f}% < {min_win_rate}%',
                    'paused': True
                }
        
        # FILTER 2: Check FVG Exists
        if pd.isna(latest.get('fvg_type')) or latest.get('fvg_type') == 'none':
            return {'type': 'NONE', 'reason': 'No FVG detected'}
        
        # FILTER 3: Strict Confluence
        conf_score = latest.get('fvg_confluence_score', 0)
        is_valid_fvg = latest.get('fvg_valid', False) and conf_score >= confluenceThreshold
        
        if not is_valid_fvg:
            return {'type': 'NONE', 'reason': f'Confluence too low ({conf_score:.0f} < {confluenceThreshold})'}
        
        fvg_type = latest.get('fvg_type')
        
        # FILTER 4: HTF Bias Alignment (if enabled)
        if self.config['enable_htf_filter']:
            if fvg_type == 'bullish' and htf_bias < 0:
                return {'type': 'NONE', 'reason': 'Bullish FVG but HTF bias is BEARISH'}
            if fvg_type == 'bearish' and htf_bias > 0:
                return {'type': 'NONE', 'reason': 'Bearish FVG but HTF bias is BULLISH'}
        
        # FILTER 5: ADX Trend Filter (if enabled)
        if self.config['enable_adx_filter']:
            adx = latest.get('adx', 0)
            if adx < 20:
                return {'type': 'NONE', 'reason': f'Weak trend (ADX {adx:.1f} < 20)'}
        
        # FILTER 6: Volume Filter (if enabled)
        if self.config['enable_volume_filter']:
            volume_ratio = latest.get('volume', 0) / latest.get('volume_ma', 1) if latest.get('volume_ma', 0) > 0 else 0
            if volume_ratio < 0.8:
                return {'type': 'NONE', 'reason': f'Low volume ({volume_ratio:.1%} of avg)'}
        
        # FILTER 7: RSI Extremes
        rsi = latest.get('rsi', 50)
        atr = latest.get('atr', latest['close'] * 0.01)
        close = latest['close']
        adx = latest.get('adx', 0)
        
        rr_ratio = self.config['risk_reward_ratio']
        
        # BULLISH SIGNAL
        if fvg_type == 'bullish':
            if rsi > 70:
                return {'type': 'NONE', 'reason': f'RSI overbought ({rsi:.1f})'}
            
            has_bos = latest.get('bos_bullish', False)
            has_order_block = latest.get('order_block_bullish', False)
            
            entry = latest.get('fvg_upper', close) + (atr * 0.1)
            if has_order_block:
                stop_loss = latest.get('ob_low', latest.get('fvg_lower', close)) - (atr * 0.1)
            else:
                stop_loss = latest.get('fvg_lower', close) - (atr * 0.15)
            
            risk = entry - stop_loss
            take_profit = entry + (risk * rr_ratio)
            
            bos_text = " + BOS" if has_bos else ""
            ob_text = " + OB" if has_order_block else ""
            
            # Check similar setup cooldown
            block, block_reason = self.trade_executor.trade_memory.should_avoid_similar_setup(
                timeframe=timeframe,
                direction='BUY',
                fvg_type='bullish',
                rsi=rsi,
                confluence_score=conf_score,
                htf_bias=htf_bias,
                cooldown_hours=72,
            )
            if block:
                return {'type': 'NONE', 'blocked_reason': block_reason}
            
            return {
                'type': 'BUY',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'reason': f"Bullish FVG ({conf_score:.0f} conf){bos_text}{ob_text} + RSI {rsi:.1f} + ADX {adx:.1f} + HTF✅ | R:R 1:{rr_ratio}"
            }
        
        # BEARISH SIGNAL
        if fvg_type == 'bearish':
            if rsi < 30:
                return {'type': 'NONE', 'reason': f'RSI oversold ({rsi:.1f})'}
            
            has_bos = latest.get('bos_bearish', False)
            has_order_block = latest.get('order_block_bearish', False)
            
            entry = latest.get('fvg_lower', close) - (atr * 0.1)
            if has_order_block:
                stop_loss = latest.get('ob_high', latest.get('fvg_upper', close)) + (atr * 0.1)
            else:
                stop_loss = latest.get('fvg_upper', close) + (atr * 0.15)
            
            risk = stop_loss - entry
            take_profit = entry - (risk * rr_ratio)
            
            bos_text = " + BOS" if has_bos else ""
            ob_text = " + OB" if has_order_block else ""
            
            # Check similar setup cooldown
            block, block_reason = self.trade_executor.trade_memory.should_avoid_similar_setup(
                timeframe=timeframe,
                direction='SELL',
                fvg_type='bearish',
                rsi=rsi,
                confluence_score=conf_score,
                htf_bias=htf_bias,
                cooldown_hours=72,
            )
            if block:
                return {'type': 'NONE', 'blocked_reason': block_reason}
            
            return {
                'type': 'SELL',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'reason': f"Bearish FVG ({conf_score:.0f} conf){bos_text}{ob_text} + RSI {rsi:.1f} + ADX {adx:.1f} + HTF✅ | R:R 1:{rr_ratio}"
            }
        
        return {'type': 'NONE', 'reason': 'No valid setup'}
    
    def scan_timeframe(self, timeframe, combined_bias):
        """Scan a single timeframe for trade opportunities"""
        try:
            # Determine confluence threshold based on timeframe
            tf_confluence = {
                '1w': max(20, self.config['min_confluence_threshold'] - 25),
                '1d': max(25, self.config['min_confluence_threshold'] - 20),
                '4h': max(30, self.config['min_confluence_threshold'] - 15),
                '2h': self.config['min_confluence_threshold'] - 10,
                '1h': self.config['min_confluence_threshold'],
                '15m': self.config['min_confluence_threshold'] + 5,
                '5m': self.config['min_confluence_threshold'] + 15,
                '1m': self.config['min_confluence_threshold'] + 20
            }
            adj_confluence = tf_confluence.get(timeframe, self.config['min_confluence_threshold'])
            
            # Fetch data
            candle_limits = {'1h': 500, '15m': 1000, '5m': 1200, '1m': 1200}
            limit = candle_limits.get(timeframe, 500)
            
            df = self.fetcher.fetch_historical_data(timeframe=timeframe, limit=limit)
            
            if df is None or len(df) < 5:
                logger.warning(f"⚠️ {timeframe}: Insufficient data")
                return None
            
            # Apply SMC indicators
            df = SMCIndicators.engineer_all_features(
                df,
                htf_bias=combined_bias,
                min_confluence_threshold=adj_confluence
            )
            
            # Generate signal (need to inject safety settings into trade executor)
            signal = self.generate_signal_with_filters(df, timeframe, combined_bias, adj_confluence)
            
            latest = df.iloc[-1]
            
            if signal['type'] != 'NONE':
                logger.info(f"🎯 {timeframe}: {signal['type']} SIGNAL - {signal.get('reason', 'N/A')}")
                
                # Execute trade
                trade_id = self.trade_executor.execute_trade(signal, df, timeframe)
                
                if trade_id:
                    logger.info(f"✅ {timeframe}: TRADE #{trade_id} EXECUTED!")
                    logger.info(f"   Entry: ${signal['entry']:,.2f} | SL: ${signal['stop_loss']:,.2f} | TP: ${signal['take_profit']:,.2f}")
                    return trade_id
                else:
                    logger.info(f"⏭️ {timeframe}: Signal generated but trade skipped (duplicate/limit)")
            else:
                reason = signal.get('reason', signal.get('blocked_reason', 'No conditions met'))
                if 'paused' in signal:
                    logger.warning(f"⛔ {timeframe}: {reason}")
                else:
                    logger.debug(f"⏳ {timeframe}: {reason}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ {timeframe}: Error scanning - {str(e)}")
            return None
    
    def update_open_trades(self):
        """Check and update all open trades"""
        open_trades = self.trade_executor.trade_memory.get_open_trades()
        
        if not open_trades:
            return
        
        logger.info(f"📊 Monitoring {len(open_trades)} open trades...")
        
        for trade_row in open_trades:
            trade_id = trade_row[0]
            timeframe = trade_row[1]
            
            try:
                # Fetch latest data for this timeframe
                df = self.fetcher.fetch_historical_data(timeframe=timeframe, limit=50)
                
                if df is not None and len(df) > 0:
                    current_price = df.iloc[-1]['close']
                    current_high = df.iloc[-1]['high']
                    current_low = df.iloc[-1]['low']
                    
                    # Update trade status
                    closed_trades = self.trade_executor.update_open_trades(
                        current_price,
                        candle_high=current_high,
                        candle_low=current_low
                    )
                    
                    if closed_trades:
                        for closed_id, result, pnl in closed_trades:
                            if result == 'WIN':
                                logger.info(f"✅ Trade #{closed_id} WON! P&L: ${pnl:,.2f}")
                            else:
                                logger.warning(f"❌ Trade #{closed_id} LOST! P&L: ${pnl:,.2f}")
            
            except Exception as e:
                logger.error(f"❌ Error updating trade #{trade_id}: {e}")
    
    def run_scan_cycle(self):
        """Run one complete scan cycle across all timeframes"""
        logger.info("\n" + "="*80)
        logger.info(f"🔍 STARTING SCAN CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        
        # Update open trades first
        self.update_open_trades()
        
        # Get HTF bias
        combined_bias = self.get_combined_htf_bias()
        bias_label = "🟢 BULLISH" if combined_bias == 1 else "🔴 BEARISH" if combined_bias == -1 else "⚪ NEUTRAL"
        logger.info(f"📈 HTF Bias: {bias_label}")
        
        # Check overall stats
        stats = self.trade_executor.trade_memory.get_overall_stats()
        if stats['total_trades'] > 0:
            logger.info(f"📊 Overall Stats: {stats['total_trades']} trades | Win Rate: {stats['win_rate']:.1f}% | P&L: ${stats['total_pnl']:,.2f}")
        
        # Scan each timeframe
        signals_found = 0
        for timeframe in self.config['timeframes_to_scan']:
            result = self.scan_timeframe(timeframe, combined_bias)
            if result:
                signals_found += 1
        
        logger.info(f"✨ Scan cycle complete - {signals_found} new trades executed")
        logger.info("="*80 + "\n")
    
    def run(self):
        """Main loop - runs indefinitely"""
        logger.info("🚀 BOT STARTED - Running 24/7 mode")
        logger.info(f"⏱️ Next scan in {self.config['scan_interval_seconds']} seconds...")
        
        try:
            while self.running:
                try:
                    self.run_scan_cycle()
                    
                    # Wait for next scan
                    time.sleep(self.config['scan_interval_seconds'])
                    
                except KeyboardInterrupt:
                    logger.info("\n⏸️ Keyboard interrupt received - shutting down gracefully...")
                    self.running = False
                    break
                
                except Exception as e:
                    logger.error(f"❌ Error in scan cycle: {e}")
                    logger.error("⏳ Waiting 60 seconds before retry...")
                    time.sleep(60)
        
        except Exception as e:
            logger.critical(f"💥 CRITICAL ERROR: {e}")
        
        finally:
            logger.info("🛑 BOT STOPPED")
            logger.info(f"Final Stats: {self.trade_executor.trade_memory.get_overall_stats()}")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    logger.info("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║          24/7 HEADLESS TRADING BOT                           ║
    ║          Smart Money Concepts + ML Learning                   ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    bot = HeadlessTradingBot(CONFIG)
    bot.run()
