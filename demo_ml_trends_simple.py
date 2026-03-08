#!/usr/bin/env python3
"""
Quick Demo: ML Trend Analysis on Live Bitcoin Data
Shows the ML module working with real market data (Windows compatible)
"""

import sys
from datetime import datetime

print("=" * 70)
print("ML TREND ANALYZER - LIVE DEMO")
print("=" * 70)

print("\n[1/3] Fetching live Bitcoin data from Binance...")
try:
    from app import BinanceDataFetcher, SMCIndicators
    
    fetcher = BinanceDataFetcher()
    df = fetcher.fetch_historical_data(timeframe='1h', limit=500)
    
    if df is None or df.empty:
        print("  [!] No data fetched (network issue or API limit)")
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
        print("  [OK] Demo data created (500 candles)")
    else:
        print("[OK] Fetched {} candles of Bitcoin 1h data".format(len(df)))
        print("     Price range: ${:.2f} - ${:.2f}".format(df['low'].min(), df['high'].max()))

except Exception as e:
    print("  [ERROR] {}".format(e))
    sys.exit(1)

print("\n[2/3] Calculating technical indicators...")
try:
    df = SMCIndicators.engineer_all_features(df, htf_bias=1)
    print("  [OK] SMC indicators calculated")
    print("     - Swing points identified")
    print("     - Fair Value Gaps (FVG) detected")
    print("     - Break of Structure (BOS) marked")
    print("     - Order Blocks identified")
    
except Exception as e:
    print("  [ERROR] {}".format(e))
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
    print("\n  Training ML models...")
    training_results = analyzer.train_trend_models(df)
    
    if training_results:
        print("  [OK] Models trained!")
        print("       Accuracy:  {:.2%}".format(training_results['accuracy']))
        print("       Precision: {:.2%}".format(training_results['precision']))
        print("       Recall:    {:.2%}".format(training_results['recall']))
        print("       F1 Score:  {:.2%}".format(training_results['f1']))
    
    # Predict current trend
    print("\n  Predicting current trend...")
    trend_pred = analyzer.predict_trend(df)
    
    if trend_pred:
        trend = trend_pred['trend']
        confidence = trend_pred['confidence']
        strength = trend_pred['strength']
        
        print("  [TREND] {}".format(trend))
        print("          Confidence: {:.1%}".format(confidence))
        print("          Strength: {:+.4f}".format(strength))
        
        # Probability distribution
        print("\n          Probability Distribution:")
        for trend_name, prob in sorted(trend_pred['probabilities'].items(), 
                                       key=lambda x: x[1], reverse=True):
            bar = "#" * int(prob * 20)
            print("          {:12s} [{}] {:.1%}".format(trend_name, bar, prob))
    
    # Identify regime
    print("\n  Identifying market regime...")
    regime = analyzer.identify_trend_regime(df, period=20)
    
    if regime:
        regime_type = regime['regime']
        
        print("  [REGIME] {}".format(regime_type))
        print("           Confidence: {:.1%}".format(regime['confidence']))
        print("           Support Level: ${:.2f}".format(regime['support']))
        print("           Resistance Level: ${:.2f}".format(regime['resistance']))
        print("           Momentum: {:+.4f}".format(regime['momentum']))
    
    # Detect reversals
    print("\n  Detecting potential reversals...")
    reversals = analyzer.detect_reversals(df)
    
    if reversals:
        for reversal in reversals:
            signal = reversal.get('signal', 'Unknown')
            prob = reversal.get('probability', 0)
            prob_indicator = "[HIGH]" if prob > 0.65 else "[MED]" if prob > 0.35 else "[LOW]"
            print("  [REVERSAL] {} {} - {:.0%}".format(prob_indicator, reversal['type'], prob))
            print("             -> {}".format(signal))
    else:
        print("  [OK] No reversals detected - trend appears intact")
    
    # Momentum analysis
    print("\n  Analyzing momentum...")
    df_mom = MomentumAnalyzer.calculate_momentum_oscillator(df)
    df_mom = MomentumAnalyzer.detect_momentum_divergence(df_mom)
    
    latest = df_mom.iloc[-1]
    osc = latest.get('momentum_oscillator', 0)
    sig = latest.get('momentum_signal', 0)
    divergence_type = latest.get('divergence_type', 'none')
    has_div = latest.get('momentum_divergence', False)
    
    print("  Momentum Oscillator: {:+.4f}".format(osc))
    print("  Signal Line: {:+.4f}".format(sig))
    if has_div:
        print("  [WARNING] Divergence detected: {}".format(divergence_type.upper()))
    else:
        print("  [OK] No divergence")
    
    # Confluence score
    print("\n  Calculating confluence score...")
    score = TrendConfluenceScorer.calculate_confluence_score(df)
    
    score_indicator = "[***|*] HIGH" if score >= 80 else "[**|**] MEDIUM" if score >= 60 else "[*|***] LOW"
    
    print("  Confidence Score: {}/100 {}".format(score, score_indicator))
    if score >= 80:
        print("       [OK] High confidence - strong signal")
    elif score >= 60:
        print("       [*] Medium confidence - moderate signal")
    else:
        print("       [!] Low confidence - wait for better setup")
    
    # Log prediction
    analyzer.log_prediction(datetime.now(), '1h', trend_pred, score)
    print("\n  [OK] Prediction logged to database")

except Exception as e:
    print("  [ERROR] {}".format(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("SUCCESS - ML DEMO COMPLETE!")
print("=" * 70)

print("\nNext Steps:")
print("  1. Run backtesting example:  python ml_backtest_examples.py")
print("  2. See documentation:        ML_BACKTEST_GUIDE.md")
print("  3. Run verification:         python verify_setup.py")
print("  4. Check results database:   backtest_results.db")

print("\nFiles Created:")
print("  - ml_trends.db               (ML predictions)")
print("  - backtest_results.db        (Backtest results)")
print("  - trend_ml_data_v3.db        (Training data)")

print("\n" + "=" * 70)
