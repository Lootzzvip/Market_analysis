"""
Example: Using ML Trend Analysis and Backtesting
Demonstrates how to use the new ML and backtesting modules
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app import BinanceDataFetcher, SMCIndicators, TrendMLDatabase, TradeExecutor
from ml_trend_analyzer import MLTrendAnalyzer, TrendConfluenceScorer, MomentumAnalyzer
from backtest_engine import BacktestEngine, StrategyOptimizer, PerformanceAnalyzer

# ==============================================================================
# EXAMPLE 1: ML TREND ANALYSIS ON LIVE DATA
# ==============================================================================

def example_ml_trend_analysis():
    """Analyze trends using machine learning on current market data"""
    print("\n" + "="*70)
    print("EXAMPLE 1: ML TREND ANALYSIS")
    print("="*70)
    
    # Fetch live data
    fetcher = BinanceDataFetcher()
    df = fetcher.fetch_historical_data(timeframe='1h', limit=500)
    
    if df is None or df.empty:
        print("❌ Failed to fetch data")
        return
    
    # Calculate SMC indicators
    df = SMCIndicators.engineer_all_features(df, htf_bias=1, min_confluence_threshold=60)
    
    # Initialize ML Trend Analyzer
    ml_analyzer = MLTrendAnalyzer()
    
    # Train models on historical data
    print("\n🤖 Training ML models...")
    training_results = ml_analyzer.train_trend_models(df)
    
    if training_results:
        print(f"   ✅ Model trained successfully!")
        print(f"   Accuracy: {training_results['accuracy']:.2%}")
        print(f"   Precision: {training_results['precision']:.2%}")
        print(f"   Recall: {training_results['recall']:.2%}")
        print(f"   F1 Score: {training_results['f1']:.2%}")
    
    # Predict current trend
    print("\n📊 Predicting current trend...")
    trend_prediction = ml_analyzer.predict_trend(df)
    
    if trend_prediction:
        print(f"   Trend: {trend_prediction['trend']}")
        print(f"   Confidence: {trend_prediction['confidence']:.2%}")
        print(f"   Strength: {trend_prediction['strength']:.4f}")
        print(f"   Probabilities:")
        for trend_name, prob in trend_prediction['probabilities'].items():
            print(f"      - {trend_name}: {prob:.2%}")
    
    # Identify current regime
    print("\n🔄 Identifying trend regime...")
    regime = ml_analyzer.identify_trend_regime(df, period=20)
    
    if regime:
        print(f"   Regime: {regime['regime']}")
        print(f"   Confidence: {regime['confidence']:.2%}")
        print(f"   Support Level: ${regime['support']:.2f}")
        print(f"   Resistance Level: ${regime['resistance']:.2f}")
        print(f"   Momentum: {regime['momentum']:.4f}")
    
    # Detect reversals
    print("\n⚡ Detecting potential reversals...")
    reversals = ml_analyzer.detect_reversals(df)
    
    if reversals:
        for reversal in reversals:
            prob = reversal.get('probability', 0)
            print(f"   {reversal['type']}: {prob:.2%} probability")
            print(f"      → {reversal.get('signal', 'N/A')}")
    else:
        print("   No reversals detected at this time")
    
    # Calculate momentum indicators
    print("\n📈 Analyzing momentum...")
    df_momentum = MomentumAnalyzer.calculate_momentum_oscillator(df, fast=12, slow=26)
    df_momentum = MomentumAnalyzer.calculate_rate_of_change(df_momentum, period=12)
    df_momentum = MomentumAnalyzer.detect_momentum_divergence(df_momentum, period=14)
    
    latest = df_momentum.iloc[-1]
    print(f"   Momentum Oscillator: {latest.get('momentum_oscillator', 0):.4f}")
    print(f"   Rate of Change: {latest.get('roc', 0):.2f}%")
    print(f"   Divergence: {latest.get('divergence_type', 'none') if latest.get('momentum_divergence', False) else 'None'}")
    
    # Calculate confluence score
    print("\n🎯 Calculating confluence score...")
    confluence_score = TrendConfluenceScorer.calculate_confluence_score(df)
    print(f"   Confidence Score: {confluence_score}/100")
    
    # Log prediction
    ml_analyzer.log_prediction(datetime.now(), '1h', trend_prediction, confluence_score)
    print("   ✅ Prediction logged to database")


# ==============================================================================
# EXAMPLE 2: BACKTESTING SMC FVG STRATEGY
# ==============================================================================

def example_backtest_fvg_strategy():
    """Backtest the SMC FVG strategy"""
    print("\n" + "="*70)
    print("EXAMPLE 2: BACKTESTING FVG STRATEGY")
    print("="*70)
    
    # Fetch historical data
    fetcher = BinanceDataFetcher()
    df = fetcher.fetch_historical_data(timeframe='4h', limit=500)
    
    if df is None or df.empty:
        print("❌ Failed to fetch data")
        return
    
    # Calculate all features
    df = SMCIndicators.engineer_all_features(df, htf_bias=1)
    
    # Define FVG strategy function
    def fvg_strategy(data):
        """Trading strategy based on valid FVGs"""
        if len(data) < 5:
            return {'type': 'NONE'}
        
        latest = data.iloc[-1]
        
        # Check for valid FVG
        if not latest.get('fvg_valid', False):
            return {'type': 'NONE'}
        
        conf_score = latest.get('fvg_confluence_score', 0)
        rsi = latest.get('rsi', 50)
        atr = latest.get('atr', latest['close'] * 0.01)
        
        # Bullish FVG signal
        if latest.get('fvg_type') == 'bullish' and rsi < 80 and conf_score > 60:
            entry = latest.get('fvg_upper', latest['close']) + (atr * 0.1)
            stop_loss = latest.get('fvg_lower', latest['close']) - (atr * 0.15)
            risk = entry - stop_loss
            
            return {
                'type': 'BUY',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': entry + (risk * 2)
            }
        
        # Bearish FVG signal
        if latest.get('fvg_type') == 'bearish' and rsi > 20 and conf_score > 60:
            entry = latest.get('fvg_lower', latest['close']) - (atr * 0.1)
            stop_loss = latest.get('fvg_upper', latest['close']) + (atr * 0.15)
            risk = stop_loss - entry
            
            return {
                'type': 'SELL',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': entry - (risk * 2)
            }
        
        return {'type': 'NONE'}
    
    # Run backtest
    print("\n🔄 Running backtest with $10,000 initial capital...")
    backtest_engine = BacktestEngine(initial_capital=10000)
    result = backtest_engine.run_backtest(df, fvg_strategy, '4h', 'FVG_Strategy_v1')
    
    # Display results
    print("\n📊 Backtest Results:")
    print(f"   Period: {result['start_date']} to {result['end_date']}")
    print(f"   Total Trades: {result['total_trades']}")
    print(f"   Winning Trades: {result['winning_trades']} ({result['win_rate']:.1f}%)")
    print(f"   Losing Trades: {result['losing_trades']}")
    print(f"   Profit Factor: {result['profit_factor']:.2f}")
    print(f"\n💰 Returns:")
    print(f"   Initial Capital: ${result['initial_capital']:,.2f}")
    print(f"   Final Equity: ${result['final_equity']:,.2f}")
    print(f"   Total Return: ${result['total_return']:,.2f}")
    print(f"   Return %: {result['total_return_pct']:.2f}%")
    print(f"\n📈 Risk Metrics:")
    print(f"   Max Drawdown: {result['max_drawdown']:.2%}")
    print(f"   Sharpe Ratio: {result['sharpe_ratio']:.2f}")
    print(f"   Sortino Ratio: {result['sortino_ratio']:.2f}")
    print(f"\n📉 Trade Stats:")
    print(f"   Avg Trade P&L: ${result['avg_trade_pnl']:,.2f}")
    print(f"   Avg Win: ${result['avg_win']:,.2f}")
    print(f"   Avg Loss: ${result['avg_loss']:,.2f}")
    print(f"   Best Trade: ${result['best_trade']:,.2f}")
    print(f"   Worst Trade: ${result['worst_trade']:,.2f}")
    
    # Save results
    run_id = backtest_engine.save_backtest_result(result)
    print(f"\n✅ Results saved with Run ID: {run_id}")
    
    return backtest_engine, result


# ==============================================================================
# EXAMPLE 3: STRATEGY OPTIMIZATION
# ==============================================================================

def example_strategy_optimization():
    """Optimize strategy parameters"""
    print("\n" + "="*70)
    print("EXAMPLE 3: STRATEGY OPTIMIZATION")
    print("="*70)
    
    # Fetch data
    fetcher = BinanceDataFetcher()
    df = fetcher.fetch_historical_data(timeframe='1h', limit=500)
    
    if df is None or df.empty:
        print("❌ Failed to fetch data")
        return
    
    # Calculate features
    df = SMCIndicators.engineer_all_features(df, htf_bias=1)
    
    backtest_engine = BacktestEngine(initial_capital=10000)
    
    # Optimize confluence threshold
    print("\n🔧 Optimizing confluence threshold...")
    print("   Testing thresholds: 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95")
    
    threshold_results = StrategyOptimizer.optimize_confluence_threshold(
        df, backtest_engine, '1h',
        thresholds=list(range(40, 100, 5))
    )
    
    print(f"\n   ✅ Best confluence threshold: {threshold_results['best_threshold']}")
    best = threshold_results['best_result']
    print(f"      Trades: {best['total_trades']}")
    print(f"      Win Rate: {best['win_rate']:.1f}%")
    print(f"      Sharpe Ratio: {best['sharpe_ratio']:.2f}")
    print(f"      Return: {best['total_return_pct']:.2f}%")
    
    # Compare optimization results
    print("\n📊 Optimization Summary:")
    results_df = pd.DataFrame([
        {
            'threshold': r['threshold'],
            'trades': r['total_trades'],
            'win_rate': r['win_rate'],
            'profit_factor': r['profit_factor'],
            'sharpe': r['sharpe_ratio'],
            'return': r['total_return_pct']
        } for r in threshold_results['all_results']
    ])
    
    print(results_df.to_string(index=False))


# ==============================================================================
# EXAMPLE 4: MULTIPLE TIMEFRAME ANALYSIS
# ==============================================================================

def example_multitimeframe_analysis():
    """Analyze trends across multiple timeframes"""
    print("\n" + "="*70)
    print("EXAMPLE 4: MULTI-TIMEFRAME ANALYSIS")
    print("="*70)
    
    fetcher = BinanceDataFetcher()
    timeframes = ['15m', '1h', '4h', '1d']
    
    ml_analyzer = MLTrendAnalyzer()
    results = {}
    
    print("\nAnalyzing trends across timeframes...")
    
    for tf in timeframes:
        print(f"\n📊 {tf.upper()}:")
        df = fetcher.fetch_historical_data(timeframe=tf, limit=200)
        
        if df is None or df.empty:
            print(f"   ❌ No data")
            continue
        
        df = SMCIndicators.engineer_all_features(df, htf_bias=1)
        
        # Train and predict
        ml_analyzer.train_trend_models(df)
        prediction = ml_analyzer.predict_trend(df)
        regime = ml_analyzer.identify_trend_regime(df)
        
        if prediction and regime:
            results[tf] = {
                'trend': prediction['trend'],
                'confidence': prediction['confidence'],
                'regime': regime['regime'],
                'support': regime['support'],
                'resistance': regime['resistance']
            }
            
            print(f"   Trend: {prediction['trend']} ({prediction['confidence']:.2%} confidence)")
            print(f"   Regime: {regime['regime']}")
            print(f"   Support: ${regime['support']:.2f}")
            print(f"   Resistance: ${regime['resistance']:.2f}")
    
    # Alignment analysis
    print("\n🔄 Multi-Timeframe Alignment:")
    all_trends = [r['trend'] for r in results.values()]
    if all_trends:
        bullish_count = sum(1 for t in all_trends if 'Bull' in t)
        bearish_count = sum(1 for t in all_trends if 'Bear' in t)
        
        alignment = "Strong Bullish" if bullish_count >= 3 else "Strong Bearish" if bearish_count >= 3 else "Mixed"
        print(f"   Overall alignment: {alignment}")
        print(f"   Bullish timeframes: {bullish_count}/{len(timeframes)}")
        print(f"   Bearish timeframes: {bearish_count}/{len(timeframes)}")


# ==============================================================================
# EXAMPLE 5: PERFORMANCE COMPARISON
# ==============================================================================

def example_performance_comparison():
    """Compare different strategy versions"""
    print("\n" + "="*70)
    print("EXAMPLE 5: PERFORMANCE COMPARISON")
    print("="*70)
    
    # Load backtest history
    backtest_engine = BacktestEngine()
    history = backtest_engine.get_backtest_history(limit=5)
    
    if history.empty:
        print("No backtest history found. Run Example 2 first.")
        return
    
    print("\n📊 Recent Backtest Results:")
    print(history[['run_id', 'strategy_name', 'total_trades', 'win_rate', 
                   'profit_factor', 'sharpe_ratio', 'total_return_pct']].to_string(index=False))
    
    # Generate summary
    print("\n📈 Performance Summary:")
    summary = PerformanceAnalyzer.generate_summary_report(history.to_dict('records'))
    
    print(f"   Total Backtests: {summary.get('num_backtests', 0)}")
    print(f"   Total Trades: {summary.get('total_trades', 0)}")
    print(f"   Average Win Rate: {summary.get('avg_win_rate', 0):.1f}%")
    print(f"   Average Profit Factor: {summary.get('avg_profit_factor', 0):.2f}")
    print(f"   Average Sharpe Ratio: {summary.get('avg_sharpe_ratio', 0):.2f}")


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖 ML TREND ANALYZER & BACKTESTING EXAMPLES")
    print("="*70)
    
    # Run examples
    print("\nRunning examples...\n")
    
    # Example 1: ML Trend Analysis
    try:
        example_ml_trend_analysis()
    except Exception as e:
        print(f"❌ Example 1 error: {e}")
    
    # Example 2: Backtesting
    try:
        example_backtest_fvg_strategy()
    except Exception as e:
        print(f"❌ Example 2 error: {e}")
    
    # Example 3: Optimization
    try:
        example_strategy_optimization()
    except Exception as e:
        print(f"❌ Example 3 error: {e}")
    
    # Example 4: Multi-timeframe
    try:
        example_multitimeframe_analysis()
    except Exception as e:
        print(f"❌ Example 4 error: {e}")
    
    # Example 5: Performance comparison
    try:
        example_performance_comparison()
    except Exception as e:
        print(f"❌ Example 5 error: {e}")
    
    print("\n" + "="*70)
    print("✅ Examples completed!")
    print("="*70)
