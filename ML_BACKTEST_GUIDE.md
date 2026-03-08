# ML Trend Analyzer & Backtesting Framework

## 📊 Overview

Your trading bot now has two powerful new modules:

1. **ML Trend Analyzer** - Machine Learning-based trend classification and prediction
2. **Backtesting Engine** - Complete framework for testing and optimizing strategies

---

## 🤖 ML Trend Analyzer (`ml_trend_analyzer.py`)

### Features

#### 1. **MLTrendAnalyzer Class**
Advanced machine learning for trend classification and prediction.

**Key Methods:**

- `train_trend_models(df)` - Train ML models on historical data
  - Returns: accuracy, precision, recall, F1 score
  - Uses Random Forest for trend classification
  
- `predict_trend(df)` - Predict current trend
  - Returns: trend type, confidence, strength, probabilities
  - Output trends: "Strong Bear", "Bear", "Sideways", "Bull", "Strong Bull"
  
- `identify_trend_regime(df, period=20)` - Identify current market regime
  - Returns: regime type, confidence, support/resistance levels
  - Regimes: "Uptrend", "Downtrend", "Sideways"
  
- `detect_reversals(df)` - Detect potential trend reversals
  - Returns: reversal type, probability, signal description
  - Detects: overbought conditions, price extremes, RSI divergences

**Features Used for ML:**
- Price action (SMA, EMA ratios)
- Momentum (RSI, MACD, Rate of Change)
- Volatility (ATR, standard deviation)
- Trend strength (multiple timeframe analysis)
- Reversal signals

**Example:**
```python
from ml_trend_analyzer import MLTrendAnalyzer

analyzer = MLTrendAnalyzer()

# Train models
training_results = analyzer.train_trend_models(df)
print(f"Accuracy: {training_results['accuracy']:.2%}")

# Predict trend
prediction = analyzer.predict_trend(df)
print(f"Trend: {prediction['trend']}")
print(f"Confidence: {prediction['confidence']:.2%}")

# Detect reversals
reversals = analyzer.detect_reversals(df)
for reversal in reversals:
    print(f"{reversal['type']}: {reversal['probability']:.2%}")
```

#### 2. **MomentumAnalyzer Class**
Analyze momentum and detect divergences.

**Methods:**
- `calculate_momentum_oscillator(df, fast=12, slow=26)` - MACD-like oscillator
- `calculate_rate_of_change(df, period=12)` - ROC indicator
- `detect_momentum_divergence(df, period=14)` - Detect bullish/bearish divergences

**Example:**
```python
from ml_trend_analyzer import MomentumAnalyzer

df = MomentumAnalyzer.calculate_momentum_oscillator(df)
df = MomentumAnalyzer.detect_momentum_divergence(df)

if df.iloc[-1]['momentum_divergence']:
    divergence_type = df.iloc[-1]['divergence_type']
    print(f"Divergence detected: {divergence_type}")
```

#### 3. **TrendConfluenceScorer Class**
Score confidence levels based on multiple indicators.

**Methods:**
- `calculate_confluence_score(df)` - Calculate 0-100 confidence score

Scoring breakdown:
- EMA convergence: 0-15 points
- RSI alignment: 0-15 points
- ADX trend strength: 0-15 points
- ATR volatility: 0-10 points
- Volume: 0-20 points
- Technical structure (BOS/ChoCh/OB): 0-10 points

**Example:**
```python
from ml_trend_analyzer import TrendConfluenceScorer

score = TrendConfluenceScorer.calculate_confluence_score(df)
print(f"Confidence: {score}/100")
```

---

## 📈 Backtesting Engine (`backtest_engine.py`)

### Features

#### 1. **BacktestEngine Class**
Complete backtesting framework for testing trading strategies.

**Key Methods:**

- `run_backtest(df, strategy_func, timeframe, strategy_name)` - Run complete backtest
  - Takes strategy function that generates signals
  - Returns: all performance metrics, trades, equity curve
  
- `save_backtest_result(result)` - Save results to database
  
- `get_backtest_history(strategy_name, limit=10)` - Retrieve past results
  
- `compare_backtests(run_ids)` - Compare multiple backtest runs

**Performance Metrics Calculated:**
- Total trades, wins, losses, win rate
- Profit factor (wins vs losses ratio)
- Total return and return percentage
- Maximum drawdown
- Sharpe ratio (risk-adjusted returns)
- Sortino ratio (downside-adjusted returns)
- Average trade P&L
- Best and worst trades
- Consecutive wins/losses

**Example:**
```python
from backtest_engine import BacktestEngine

def my_strategy(data):
    """Returns {'type': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'tp': price}"""
    if len(data) < 5:
        return {'type': 'NONE'}
    
    latest = data.iloc[-1]
    
    if latest['rsi'] < 30:
        return {
            'type': 'BUY',
            'entry': latest['close'],
            'stop_loss': latest['close'] * 0.99,
            'take_profit': latest['close'] * 1.02
        }
    
    return {'type': 'NONE'}

backtest = BacktestEngine(initial_capital=10000)
result = backtest.run_backtest(df, my_strategy, '1h', 'My_Strategy')

print(f"Win Rate: {result['win_rate']:.1f}%")
print(f"Profit Factor: {result['profit_factor']:.2f}")
print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")
print(f"Total Return: {result['total_return_pct']:.2f}%")
```

#### 2. **StrategyOptimizer Class**
Optimize strategy parameters automatically.

**Methods:**

- `optimize_confluence_threshold(df, backtest_engine, timeframe, thresholds)` - Find optimal confidence threshold
  
- `optimize_rsi_levels(df, backtest_engine, timeframe, rsi_levels)` - Find optimal RSI levels

**Example:**
```python
from backtest_engine import StrategyOptimizer

optimizer = StrategyOptimizer()

# Test different confluence thresholds
results = optimizer.optimize_confluence_threshold(
    df, backtest_engine, '1h',
    thresholds=list(range(40, 100, 5))
)

print(f"Best threshold: {results['best_threshold']}")
print(f"Best Sharpe Ratio: {results['best_result']['sharpe_ratio']:.2f}")
```

#### 3. **PerformanceAnalyzer Class**
Analyze and compare performance across multiple backtests.

**Methods:**

- `generate_summary_report(backtest_results)` - Generate overall summary
  
- `identify_strategy_improvements(before, after)` - Compare two strategy versions

**Example:**
```python
from backtest_engine import PerformanceAnalyzer

analyzer = PerformanceAnalyzer()
summary = analyzer.generate_summary_report(all_results)

print(f"Average Win Rate: {summary['avg_win_rate']:.1f}%")
print(f"Best Strategy: {summary['best_strategy']}")
print(f"Best Return: {summary['best_return_pct']:.2f}%")
```

---

## 🔗 Integration with Existing Code

### Using ML Trends with Your FVG Strategy

```python
from app import BinanceDataFetcher, SMCIndicators
from ml_trend_analyzer import MLTrendAnalyzer, TrendConfluenceScorer

# Fetch data
fetcher = BinanceDataFetcher()
df = fetcher.fetch_historical_data('1h', limit=500)

# Calculate SMC indicators
df = SMCIndicators.engineer_all_features(df)

# Add ML trend analysis
analyzer = MLTrendAnalyzer()
trend_pred = analyzer.predict_trend(df)

# Get confluence score
confluence = TrendConfluenceScorer.calculate_confluence_score(df)

# Use in signal generation
if df.iloc[-1]['fvg_valid'] and trend_pred['confidence'] > 0.7:
    if trend_pred['trend'] in ['Bull', 'Strong Bull'] and df.iloc[-1]['fvg_type'] == 'bullish':
        print(f"Strong bullish signal! ({confluence}/100 confidence)")
```

### Backtesting Your Existing Strategy

```python
from app import TradeExecutor
from backtest_engine import BacktestEngine

# Get executor's signal generation logic
executor = TradeExecutor()

def my_fvg_strategy(data):
    signal = executor.generate_signal(data, '1h', confluenceThreshold=60)
    return signal

# Backtest it
backtest = BacktestEngine()
result = backtest.run_backtest(df, my_fvg_strategy, '1h', 'Current_FVG_Strategy')

# Save and compare
run_id = backtest.save_backtest_result(result)
```

---

## 📊 Database Schema

### ML Trends Database (`ml_trends.db`)

**trend_predictions table:**
- timestamp: When prediction was made
- timeframe: 15m, 1h, 4h, 1d, etc.
- trend_type: Strong Bull, Bull, Sideways, Bear, Strong Bear
- trend_strength: -1.0 to 1.0
- trend_momentum: Rate of change
- confidence: 0-1
- actual_direction: Used to track accuracy over time

**trend_regime_history table:**
- timestamp, timeframe, regime_type (Uptrend/Downtrend/Sideways)
- Support/resistance levels
- Regime_confidence

### Backtest Database (`backtest_results.db`)

**backtest_runs table:**
- All performance metrics
- Strategy name, timeframe, date range
- Total return, Sharpe ratio, win rate, etc.

**backtest_trades table:**
- Individual trade records
- Entry/exit times and prices
- P&L and duration

**backtest_equity_curve table:**
- Equity at each timestamp
- Drawdown tracking

---

## 🎯 Quick Start Guide

### 1. Install Latest Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run ML Analysis on Current Market
```python
from ml_backtest_examples import example_ml_trend_analysis
example_ml_trend_analysis()
```

### 3. Backtest Your Strategy
```python
from ml_backtest_examples import example_backtest_fvg_strategy
backtest_engine, result = example_backtest_fvg_strategy()
```

### 4. Optimize Parameters
```python
from ml_backtest_examples import example_strategy_optimization
example_strategy_optimization()
```

### 5. Analyze Multiple Timeframes
```python
from ml_backtest_examples import example_multitimeframe_analysis
example_multitimeframe_analysis()
```

---

## 📈 Key Metrics Explained

### Win Rate
Percentage of profitable trades. Higher is better.
- Formula: (Winning Trades / Total Trades) × 100
- Good: > 55%

### Profit Factor
Ratio of wins to losses. Higher is better.
- Formula: Total Wins / Total Losses
- Good: > 1.5

### Sharpe Ratio
Risk-adjusted return. Higher is better.
- Formula: (Average Return - Risk Free Rate) / Standard Deviation
- > 1.0: good
- > 2.0: excellent

### Sortino Ratio
Like Sharpe, but only penalizes downside volatility.
- Good: > 1.0
- Excellent: > 1.5

### Maximum Drawdown
Largest peak-to-trough loss. Lower is better.
- Under 20%: good
- Under 10%: excellent

---

## 🔧 Advanced Usage

### Custom Strategy with ML Signals

```python
from ml_trend_analyzer import MLTrendAnalyzer, TrendConfluenceScorer
from backtest_engine import BacktestEngine

analyzer = MLTrendAnalyzer()
analyzer.train_trend_models(df_history)

def advanced_strategy(data):
    """Strategy combining ML trends with technical indicators"""
    if len(data) < 20:
        return {'type': 'NONE'}
    
    latest = data.iloc[-1]
    
    # Get ML prediction
    trend = analyzer.predict_trend(data)
    confidence = TrendConfluenceScorer.calculate_confluence_score(data)
    
    # Entry conditions
    if trend['confidence'] > 0.8 and confidence > 70:
        if 'Bull' in trend['trend'] and latest['fvg_valid']:
            return {
                'type': 'BUY',
                'entry': latest['close'],
                'stop_loss': latest['support'],
                'take_profit': latest['close'] * 1.03
            }
    
    return {'type': 'NONE'}

# Backtest advanced strategy
backtest = BacktestEngine()
result = backtest.run_backtest(df, advanced_strategy, '1h', 'Advanced_ML_Strategy')
```

### Parameter Grid Search

```python
from backtest_engine import StrategyOptimizer

results = []

for confluence in range(50, 90, 10):
    for rsi_overbought in range(70, 85, 5):
        # Define strategy with these params
        def strategy(data, conf=confluence, rsi_ob=rsi_overbought):
            # ... strategy logic using conf and rsi_ob
            pass
        
        result = backtest.run_backtest(df, strategy, '1h')
        results.append(result)

# Find best parameters
best = max(results, key=lambda x: x['sharpe_ratio'])
```

---

## 📝 Output Examples

### ML Trend Analysis Output
```
TREND: Strong Bull (87.3% confidence)
Regime: Uptrend
Support: $63,450
Resistance: $64,200
Momentum: +0.0234 (Strong positive)
Reversals: None detected

Confluence Score: 82/100
- EMA convergence: ✓
- RSI alignment: ✓
- ADX strength: ✓
- Volume support: ✓
```

### Backtest Results Output
```
Total Trades: 47
Win Rate: 64.2%
Profit Factor: 2.34
Sharpe Ratio: 1.87
Sortino Ratio: 2.14

Returns:
- Initial: $10,000
- Final: $24,650
- Total Return: +146.5%
- Max Drawdown: -18.3%

Trade Stats:
- Avg Win: $612
- Avg Loss: $261
- Best Trade: $2,840
- Worst Trade: -$1,230
- Consecutive Wins: 8
```

---

## 🐛 Troubleshooting

### Models Won't Train
- Need at least 50 valid historical candles
- Check that all required indicators are calculated
- Verify data has no NaN values in key features

### Backtests Too Slow
- Reduce historical data size (use `limit=250` instead of 1000)
- Use only 1-2 strategy variations in optimization
- Close the database connections properly

### Poor Backtest Results
- Ensure strategy function returns proper format: `{'type': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'tp': price}`
- Add stop loss - strategies without exits fail
- Validate indicators are being calculated correctly
- Check for lookahead bias (don't use future data)

---

## 📚 Additional Resources

- `ml_backtest_examples.py`: 5 complete working examples
- `ml_trend_analyzer.py`: Full ML implementation
- `backtest_engine.py`: Full backtesting framework
- databases: `ml_trends.db`, `backtest_results.db` store historical data

---

## ✅ Checklist

- [x] ML Trend Classification (5-class: Strong Bear to Strong Bull)
- [x] Momentum Divergence Detection
- [x] Reversal Probability Calculation
- [x] Multi-timeframe Regime Analysis
- [x] Complete Backtesting Framework
- [x] Automatic Performance Metrics Calculation
- [x] Parameter Optimization Tools
- [x] Strategy Comparison Tools
- [x] Equity Curve & Drawdown Tracking
- [x] Historical Result Storage

---

## 🚀 Next Steps

1. Run the examples to see output: `python ml_backtest_examples.py`
2. Refine your FVG strategy with backtest results
3. Optimize parameters for your favorite timeframe
4. Deploy improved strategy with higher confidence
5. Monitor ML predictions vs actual market movements

---

**Created**: March 2026
**Version**: 1.0
**Status**: Production Ready ✅
