# Quick Reference: ML Trends & Backtesting

## 🚀 30-Second Startup

```python
from ml_trend_analyzer import MLTrendAnalyzer
from backtest_engine import BacktestEngine
from app import BinanceDataFetcher, SMCIndicators

# 1. Get data
fetcher = BinanceDataFetcher()
df = fetcher.fetch_historical_data('1h', limit=500)

# 2. Add indicators
df = SMCIndicators.engineer_all_features(df)

# 3. Analyze trends with ML
analyzer = MLTrendAnalyzer()
prediction = analyzer.predict_trend(df)
print(f"Trend: {prediction['trend']} ({prediction['confidence']:.0%})")

# 4. Backtest strategy
backtest = BacktestEngine()
def strategy(data):
    return {'type': 'BUY' if data.iloc[-1]['rsi'] < 30 else 'NONE', 
            'entry': data.iloc[-1]['close'], 'stop_loss': data.iloc[-1]['close']*0.99, 
            'take_profit': data.iloc[-1]['close']*1.02}
result = backtest.run_backtest(df, strategy, '1h')
print(f"Return: {result['total_return_pct']:.1f}% | Sharpe: {result['sharpe_ratio']:.2f}")
```

---

## 📊 Common Tasks

### Predict Current Trend
```python
from ml_trend_analyzer import MLTrendAnalyzer

analyzer = MLTrendAnalyzer()
prediction = analyzer.predict_trend(df)

# Get trend (0-4 scale)
print(prediction['trend'])  # "Strong Bull", "Bull", "Sideways", "Bear", "Strong Bear"
print(prediction['confidence'])  # 0.0 to 1.0
print(prediction['strength'])  # -1.0 to 1.0
```

### Identify Market Regime
```python
regime = analyzer.identify_trend_regime(df, period=20)
print(f"Regime: {regime['regime']}")  # "Uptrend", "Downtrend", "Sideways"
print(f"Support: ${regime['support']:.2f}")
print(f"Resistance: ${regime['resistance']:.2f}")
```

### Detect Reversals
```python
reversals = analyzer.detect_reversals(df)
for r in reversals:
    print(f"{r['type']}: {r['probability']:.0%} - {r['signal']}")
```

### Calculate Confidence Score
```python
from ml_trend_analyzer import TrendConfluenceScorer
score = TrendConfluenceScorer.calculate_confluence_score(df)
print(f"Confidence: {score}/100")
```

### Analyze Momentum
```python
from ml_trend_analyzer import MomentumAnalyzer

df = MomentumAnalyzer.calculate_momentum_oscillator(df)
df = MomentumAnalyzer.detect_momentum_divergence(df)

if df.iloc[-1]['momentum_divergence']:
    print(f"Divergence: {df.iloc[-1]['divergence_type']}")
```

### Train ML Models
```python
results = analyzer.train_trend_models(df)
print(f"Accuracy: {results['accuracy']:.2%}")
print(f"Precision: {results['precision']:.2%}")
```

---

### Run Basic Backtest
```python
from backtest_engine import BacktestEngine

backtest = BacktestEngine(initial_capital=10000)

def simple_strategy(data):
    if len(data) < 5:
        return {'type': 'NONE'}
    latest = data.iloc[-1]
    if latest.get('fvg_valid'):
        return {
            'type': 'BUY' if latest['fvg_type'] == 'bullish' else 'SELL',
            'entry': latest['close'],
            'stop_loss': latest['support'],
            'take_profit': latest['resistance']
        }
    return {'type': 'NONE'}

result = backtest.run_backtest(df, simple_strategy, '1h', 'BacktestName')
```

### View Backtest Results
```python
print(f"Trades: {result['total_trades']}")
print(f"Win Rate: {result['win_rate']:.1f}%")
print(f"Profit Factor: {result['profit_factor']:.2f}")
print(f"Total Return: {result['total_return_pct']:.2f}%")
print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {result['max_drawdown']:.2%}")
```

### Save Backtest to Database
```python
run_id = backtest.save_backtest_result(result)
print(f"Saved as run_id: {run_id}")
```

### View Past Backtests
```python
history = backtest.get_backtest_history(strategy_name='FVG_Strategy', limit=10)
print(history[['strategy_name', 'win_rate', 'sharpe_ratio', 'total_return_pct']])
```

### Compare Backtests
```python
comparison = backtest.compare_backtests([run_id_1, run_id_2, run_id_3])
print(comparison[['strategy_name', 'win_rate', 'total_return_pct']])
```

### Optimize Strategy Parameters
```python
from backtest_engine import StrategyOptimizer

optimizer = StrategyOptimizer()

# Find best confluence threshold
results = optimizer.optimize_confluence_threshold(
    df, backtest, '1h',
    thresholds=list(range(40, 100, 5))
)
print(f"Best: {results['best_threshold']}")

# Find best RSI levels
results = optimizer.optimize_rsi_levels(
    df, backtest, '1h',
    rsi_levels=[(70,30), (75,25), (80,20)]
)
print(f"Best: {results['best_levels']}")
```

### Compare Strategy Versions
```python
from backtest_engine import PerformanceAnalyzer

summary = PerformanceAnalyzer.generate_summary_report([result1, result2, result3])
print(f"Best Win Rate: {summary.get('best_strategy')}")
print(f"Best Return: {summary.get('best_return_pct'):.1f}%")

# See improvements
improvements = PerformanceAnalyzer.identify_strategy_improvements(old_result, new_result)
for metric, change in improvements.items():
    print(f"{metric}: {change['change_pct']:+.1f}%")
```

---

## 📈 Advanced Combinations

### ML Trend + FVG Strategy
```python
def ml_fvg_strategy(data):
    if len(data) < 50:
        return {'type': 'NONE'}
    
    latest = data.iloc[-1]
    
    # Check FVG validity
    if not latest.get('fvg_valid'):
        return {'type': 'NONE'}
    
    # Check ML trend
    prediction = analyzer.predict_trend(data)
    score = TrendConfluenceScorer.calculate_confluence_score(data)
    
    # Only trade on high-confidence ML predictions
    if prediction['confidence'] < 0.7 or score < 70:
        return {'type': 'NONE'}
    
    # Bullish: FVG + Bullish trend
    if latest['fvg_type'] == 'bullish' and 'Bull' in prediction['trend']:
        return {
            'type': 'BUY',
            'entry': latest['close'] + (latest['atr'] * 0.1),
            'stop_loss': latest['fvg_lower'] - (latest['atr'] * 0.1),
            'take_profit': latest['close'] + (latest['atr'] * 0.3)
        }
    
    # Bearish: FVG + Bearish trend
    if latest['fvg_type'] == 'bearish' and 'Bear' in prediction['trend']:
        return {
            'type': 'SELL',
            'entry': latest['close'] - (latest['atr'] * 0.1),
            'stop_loss': latest['fvg_upper'] + (latest['atr'] * 0.1),
            'take_profit': latest['close'] - (latest['atr'] * 0.3)
        }
    
    return {'type': 'NONE'}
```

### Multi-Timeframe Analysis
```python
timeframes = ['15m', '1h', '4h', '1d']
predictions = {}

for tf in timeframes:
    df_tf = fetcher.fetch_historical_data(tf, limit=200)
    df_tf = SMCIndicators.engineer_all_features(df_tf)
    predictions[tf] = analyzer.predict_trend(df_tf)

# Count bullish timeframes
bullish_count = sum(1 for p in predictions.values() if 'Bull' in p['trend'])
print(f"Bullish TFs: {bullish_count}/{len(timeframes)}")
```

### Momentum Divergence Strategy
```python
def divergence_strategy(data):
    if len(data) < 30:
        return {'type': 'NONE'}
    
    data = MomentumAnalyzer.detect_momentum_divergence(data)
    latest = data.iloc[-1]
    
    if not latest.get('momentum_divergence'):
        return {'type': 'NONE'}
    
    # Bullish divergence = potential reversal up
    if latest['divergence_type'] == 'bullish':
        return {
            'type': 'BUY',
            'entry': latest['close'],
            'stop_loss': data.tail(20)['low'].min(),
            'take_profit': latest['close'] * 1.02
        }
    
    # Bearish divergence = potential reversal down
    if latest['divergence_type'] == 'bearish':
        return {
            'type': 'SELL',
            'entry': latest['close'],
            'stop_loss': data.tail(20)['high'].max(),
            'take_profit': latest['close'] * 0.98
        }
    
    return {'type': 'NONE'}
```

---

## 🎯 Decision Trees

### When to Use ML Trend Analysis
✅ When you want:
- Trend classification across multiple timeframes
- Confidence levels for trading decisions
- Reversal detection
- Multi-indicator confluence scoring

### When to Use Backtesting
✅ When you want to:
- Test strategy on historical data
- Optimize parameters
- Compare different strategy versions
- Calculate performance metrics

### When to Use Both Together
✅ Powerful combination:
- Backtest an ML-based strategy
- Optimize ML confidence thresholds
- Find best parameters for your market conditions

---

## 📊 Key Metrics at a Glance

| Metric | Good | Excellent |
|--------|------|-----------|
| Win Rate | >55% | >65% |
| Profit Factor | >1.5 | >2.0 |
| Sharpe Ratio | >1.0 | >2.0 |
| Sortino Ratio | >1.0 | >1.5 |
| Max Drawdown | <20% | <10% |
| Consecutive Wins | >5 | >10 |

---

## 🔧 Parameter Tuning Quick Tips

**Confluence Threshold**: Start at 60, optimize with `optimize_confluence_threshold`

**Stop Loss**: Use support level or 1-2 ATR below entry

**Take Profit**: Aim for 1:2 or 1:3 risk/reward ratio

**ML Confidence**: Set minimum 0.70 for significant changes in direction

**Timeframe**: Backtest on same timeframe you'll trade

---

## 💾 Database Files

After running:
- `ml_trends.db` - ML predictions, trends, regimes
- `backtest_results.db` - All backtest runs, trades, equity curves
- `trend_ml_data_v3.db` - Training data
- `trade_history_v1.db` - Live trade history

---

## 🐛 Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "No data fetched" | Check internet, API key, CCXT setup |
| Models won't train | Need 50+ rows, check for NaN values |
| Backtest slow | Reduce `limit` parameter, fewer timeframes |
| Bad results | Check strategy returns proper signal format |
| Database locked | Close other connections, restart Python |

---

## 📞 Support

**Check:**
1. All imports work: `python -c "from ml_trend_analyzer import MLTrendAnalyzer"`
2. Data fetching: `python ml_backtest_examples.py` (Example 1)
3. Backtest works: `python ml_backtest_examples.py` (Example 2)

**Debug:**
- Enable logging: `import logging; logging.basicConfig(level=logging.DEBUG)`
- Check databases: `ls *.db` or use SQLite client
- Verify indicators: `print(df.columns)` after features added

---

## 📚 File Structure

```
TV/
├── app.py                          # Main app (FVG strategy, SMC indicators)
├── trading_bot.py                   # Headless bot
├── ml_trend_analyzer.py            # ML trend analysis NEW
├── backtest_engine.py              # Backtesting framework NEW
├── ml_backtest_examples.py         # 5 working examples NEW
├── ML_BACKTEST_GUIDE.md            # Full documentation NEW
├── QUICK_REFERENCE.md              # This file NEW
├── requirements.txt                # Dependencies
└── *.db                            # Database files created at runtime
```

---

**Version**: 1.0  
**Status**: ✅ Production Ready  
**Last Updated**: March 2026
