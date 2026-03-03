"""
Headless Trading Bot for GitHub Actions
Runs trading logic without Streamlit UI
Use this for cloud/automated trading
"""

import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# Import core classes from app.py
import sys
sys.path.insert(0, '/app' if '/app' in __file__ else '.')

from app import (
    BinanceDataFetcher, SMCIndicators, TrendMLDatabase,
    FVGPredictor, TradeExecutor, TradeMemory
)

def run_trading_cycle(selected_timeframe='1h'):
    """Execute one complete trading cycle"""
    try:
        print(f"\n{'='*60}")
        print(f"🤖 TRADING BOT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Timeframe: {selected_timeframe.upper()}")
        print(f"{'='*60}\n")
        
        # Initialize
        fetcher = BinanceDataFetcher()
        trend_db = TrendMLDatabase()
        predictor = FVGPredictor(db=trend_db)
        trade_executor = TradeExecutor(initial_balance=10000)
        
        # Fetch data
        candle_limit = {
            '1w': 500, '1d': 500, '4h': 500, '2h': 500,
            '1h': 500, '15m': 1000, '5m': 2000
        }
        
        df = fetcher.fetch_historical_data(
            timeframe=selected_timeframe,
            limit=candle_limit.get(selected_timeframe, 500)
        )
        
        if df is None or df.empty:
            print("❌ No data fetched")
            return False
        
        # Get HTF bias
        df_4h = fetcher.fetch_historical_data(timeframe='4h', limit=500)
        df_1d = fetcher.fetch_historical_data(timeframe='1d', limit=500)
        
        bias_4h = compute_htf_bias(df_4h)
        bias_1d = compute_htf_bias(df_1d)
        
        combined_bias = bias_4h if bias_4h == bias_1d else (bias_4h if bias_4h != 0 else bias_1d)
        
        print(f"📊 HTF Bias: 4H={bias_4h}, 1D={bias_1d}, Combined={combined_bias}")
        
        # Apply features
        df = SMCIndicators.engineer_all_features(
            df,
            htf_bias=combined_bias,
            min_confluence_threshold=60
        )
        
        # Train model
        accuracy = predictor.train(df, timeframe=selected_timeframe)
        print(f"🧠 Model Accuracy: {accuracy:.2%}")
        
        # Get prediction
        latest_prob = predictor.predict_fvg_success(df)
        trend_db.log_trend_snapshot(df.iloc[-1], selected_timeframe, latest_prob)
        
        # Generate signal
        signal = trade_executor.generate_signal(
            df,
            selected_timeframe,
            confluenceThreshold=60
        )
        
        # Execute trade if signal
        if signal['type'] != 'NONE':
            trade_id = trade_executor.execute_trade(signal, df, selected_timeframe)
            if trade_id:
                print(f"✅ TRADE OPENED #{trade_id}")
                print(f"   Type: {signal['type']}")
                print(f"   Entry: ${signal['entry']:,.2f}")
                print(f"   SL: ${signal['stop_loss']:,.2f}")
                print(f"   TP: ${signal['take_profit']:,.2f}")
        else:
            print(f"⏳ No signal (Confluence/RSI conditions not met)")
        
        # Update open trades
        current_price = df.iloc[-1]['close']
        closed = trade_executor.update_open_trades(current_price)
        
        if closed:
            for trade_id, result, pnl in closed:
                status = "✅ WIN" if result == 'WIN' else "❌ LOSS"
                print(f"{status} Trade #{trade_id}: P&L ${pnl:,.2f}")
        
        # ML learning from trades
        learned = predictor.learn_from_trades(trade_executor.trade_memory)
        if learned:
            threshold = predictor.get_adaptive_confluence_threshold()
            print(f"🧠 ML Updated! Adaptive Threshold: {threshold}")
        
        # Show stats
        stats = trade_executor.trade_memory.get_stats(selected_timeframe)
        if stats and stats['total'] > 0:
            print(f"\n📈 {selected_timeframe.upper()} Stats:")
            print(f"   Total: {stats['total']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
            print(f"   Win Rate: {stats['win_rate']:.1f}% | P&L: ${stats['total_pnl']:,.2f}")
        
        print(f"\n✅ Cycle complete at {datetime.now().strftime('%H:%M:%S')}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def compute_htf_bias(df_htf):
    """Calculate higher timeframe bias"""
    if df_htf is None or df_htf.empty or len(df_htf) < 60:
        return 0
    
    ema_fast = df_htf['close'].ewm(span=20, adjust=False).mean()
    ema_slow = df_htf['close'].ewm(span=50, adjust=False).mean()
    last_close = df_htf['close'].iloc[-1]
    
    if ema_fast.iloc[-1] > ema_slow.iloc[-1] and last_close > ema_slow.iloc[-1]:
        return 1  # Bullish
    elif ema_fast.iloc[-1] < ema_slow.iloc[-1] and last_close < ema_slow.iloc[-1]:
        return -1  # Bearish
    return 0


if __name__ == "__main__":
    print("🚀 Starting headless trading bot...")
    
    # Run for all timeframes
    timeframes = ['1w', '1d', '4h', '2h', '1h', '15m', '5m']
    
    for tf in timeframes:
        run_trading_cycle(tf)
        print("\n" + "="*60 + "\n")
    
    print("✅ Trading cycle complete!")
