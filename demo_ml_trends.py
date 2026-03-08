#!/usr/bin/env python3
"""
Quick Demo: ML Trend Analysis on Live Bitcoin Data
Shows the ML module working with real market data
"""

import sys
from datetime import datetime

print("=" * 70)
print("🤖 ML TREND ANALYZER - LIVE DEMO")
print("=" * 70)

print("\n[1/3] Fetching live Bitcoin data from Binance...")
try:
    from app import BinanceDataFetcher, SMCIndicators
    
    fetcher = BinanceDataFetcher()
    df = fetcher.fetch_historical_data(timeframe='1h', limit=500)
    
    if df is None or df.empty:
        print("  ⚠️  No data fetched (network issue or API limit)")
        print("  Creating demo data...")
        import pandas as pd
        import numpy as np
        
        # Create synthetic demo data
        dates = pd.date_range(end=datetime.now(), periods=500, freq='1h')
        close_prices = 68000 + np.cumsum(np.random.randn(500) * 100)
        df = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices - np.random.rand(500) * 50,
            'high': close_prices + np.random.rand(500) * 50,
            'low': close_prices - np.random.rand(500) * 50,
            'close': close_prices,
            'volume': np.random.rand(500) * 1000
        })
        print("  ✅ Demo data created (500 candles)")
    else:
        print(f"  ✅ Fetched {len(df)} candles of Bitcoin 1h data")
        print(f"     Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")

except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

print("\n[2/3] Calculating technical indicators...")
try:
    df = SMCIndicators.engineer_all_features(df, htf_bias=1)
    print("  ✅ SMC indicators calculated")
    print(f"     - Swing points identified")
    print(f"     - Fair Value Gaps (FVG) detected")
    print(f"     - Break of Structure (BOS) marked")
    print(f"     - Order Blocks identified")
    
except Exception as e:
    print(f"  ❌ Error: {e}")
    sys.exit(1)

print("\n[3/3] Running ML Trend Analysis...")
try:
    from ml_trend_analyzer import (
        MLTrendAnalyzer, 
        MomentumAnalyzer, 
        TrendConfluenceScorer
    )
    
    analyzer = MLTrendAnalyzer()
    
    # Train ML models
    print("\n  📚 Training ML models...")
    training_results = analyzer.train_trend_models(df)
    
    if training_results:
        print(f"     ✅ Models trained!")
        print(f"        Accuracy:  {training_results['accuracy']:.2%}")
        print(f"        Precision: {training_results['precision']:.2%}")
        print(f"        Recall:    {training_results['recall']:.2%}")
        print(f"        F1 Score:  {training_results['f1']:.2%}")
    
    # Predict current trend
    print("\n  🔮 Predicting current trend...")
    trend_pred = analyzer.predict_trend(df)
    
    if trend_pred:
        trend = trend_pred['trend']
        confidence = trend_pred['confidence']
        strength = trend_pred['strength']
        
        # Emoji based on trend
        emoji_map = {
            'Strong Bull': '🟢🟢',
            'Bull': '🟢',
            'Sideways': '⚪',
            'Bear': '🔴',
            'Strong Bear': '🔴🔴'
        }
        emoji = emoji_map.get(trend, '❓')
        
        print(f"     {emoji} TREND: {trend}")
        print(f"        Confidence: {confidence:.1%}")
        print(f"        Strength: {strength:+.4f}")
        
        # Probability distribution
        print("\n        Probability Distribution:")
        for trend_name, prob in sorted(trend_pred['probabilities'].items(), 
                                       key=lambda x: x[1], reverse=True):
            bar = "█" * int(prob * 30)
            print(f"        {trend_name:12s} {bar} {prob:.1%}")
    
    # Identify regime
    print("\n  📊 Identifying market regime...")
    regime = analyzer.identify_trend_regime(df, period=20)
    
    if regime:
        regime_emoji = {
            'Uptrend': '📈',
            'Downtrend': '📉',
            'Sideways': '➡️'
        }
        
        regime_type = regime['regime']
        emoji = regime_emoji.get(regime_type, '❓')
        
        print(f"     {emoji} Regime: {regime_type}")
        print(f"        Confidence: {regime['confidence']:.1%}")
        print(f"        Support Level: ${regime['support']:.2f}")
        print(f"        Resistance Level: ${regime['resistance']:.2f}")
        print(f"        Momentum: {regime['momentum']:+.4f}")
    
    # Detect reversals
    print("\n  ⚡ Detecting potential reversals...")
    reversals = analyzer.detect_reversals(df)
    
    if reversals:
        for reversal in reversals:
            signal = reversal.get('signal', 'Unknown')
            prob = reversal.get('probability', 0)
            prob_emoji = "🟢" if prob > 0.65 else "🟡" if prob > 0.35 else "🔴"
            print(f"     {prob_emoji} {reversal['type']}: {prob:.0%}")
            print(f"        → {signal}")
    else:
        print("     ✅ No reversals detected - trend appears intact")
    
    # Momentum analysis
    print("\n  📈 Analyzing momentum...")
    df_mom = MomentumAnalyzer.calculate_momentum_oscillator(df)
    df_mom = MomentumAnalyzer.detect_momentum_divergence(df_mom)
    
    latest = df_mom.iloc[-1]
    osc = latest.get('momentum_oscillator', 0)
    sig = latest.get('momentum_signal', 0)
    divergence_type = latest.get('divergence_type', 'none')
    has_div = latest.get('momentum_divergence', False)
    
    print(f"     Momentum Oscillator: {osc:+.4f}")
    print(f"     Signal Line: {sig:+.4f}")
    if has_div:
        print(f"     ⚠️  Divergence detected: {divergence_type.upper()}")
    else:
        print(f"     ✅ No divergence")
    
    # Confluence score
    print("\n  🎯 Calculating confluence score...")
    score = TrendConfluenceScorer.calculate_confluence_score(df)
    
    score_stars = "★" * (score // 20) + "☆" * (5 - score // 20)
    score_color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    
    print(f"     {score_color} Confidence Score: {score}/100 {score_stars}")
    if score >= 80:
        print("        ✅ High confidence - strong signal")
    elif score >= 60:
        print("        ⚠️  Medium confidence - moderate signal")
    else:
        print("        ❌ Low confidence - wait for better setup")
    
    # Log prediction
    analyzer.log_prediction(datetime.now(), '1h', trend_pred, score)
    print("\n  ✅ Prediction logged to database")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ ML DEMO COMPLETE!")
print("=" * 70)

print("\n📊 Next Steps:")
print("  1. Run backtesting example:  python ml_backtest_examples.py")
print("  2. Optimize parameters:     See ML_BACKTEST_GUIDE.md")
print("  3. Test your strategy:      Use BacktestEngine")
print("  4. View results:            Check backtest_results.db")

print("\n" + "=" * 70)
