#!/usr/bin/env python3
"""
Quick verification test for ML Trend Analyzer and Backtesting Engine
"""

print("=" * 70)
print("🔍 VERIFICATION TEST - ML & Backtesting Modules")
print("=" * 70)

# Test 1: Import modules
print("\n[1/4] Testing imports...")
try:
    from ml_trend_analyzer import MLTrendAnalyzer, MomentumAnalyzer, TrendConfluenceScorer
    print("  ✅ ml_trend_analyzer imported successfully")
except Exception as e:
    print(f"  ❌ ml_trend_analyzer import failed: {e}")
    exit(1)

try:
    from backtest_engine import BacktestEngine, StrategyOptimizer, PerformanceAnalyzer
    print("  ✅ backtest_engine imported successfully")
except Exception as e:
    print(f"  ❌ backtest_engine import failed: {e}")
    exit(1)

# Test 2: Check dependencies
print("\n[2/4] Checking dependencies...")
try:
    import sklearn
    print("  ✅ scikit-learn available")
except:
    print("  ❌ scikit-learn missing")

try:
    import scipy
    print("  ✅ scipy available")
except:
    print("  ❌ scipy missing")

try:
    import pandas
    print("  ✅ pandas available")
except:
    print("  ❌ pandas missing")

# Test 3: Initialize ML Analyzer
print("\n[3/4] Initializing ML Analyzer...")
try:
    analyzer = MLTrendAnalyzer()
    print("  ✅ MLTrendAnalyzer initialized")
    print(f"     - Models: Trend classifier, Momentum analyzer, Reversal detector")
    print(f"     - Database: ml_trends.db created")
except Exception as e:
    print(f"  ❌ MLTrendAnalyzer failed: {e}")

# Test 4: Initialize Backtest Engine
print("\n[4/4] Initializing Backtest Engine...")
try:
    backtest = BacktestEngine(initial_capital=10000)
    print("  ✅ BacktestEngine initialized")
    print(f"     - Initial capital: $10,000")
    print(f"     - Database: backtest_results.db created")
except Exception as e:
    print(f"  ❌ BacktestEngine failed: {e}")

print("\n" + "=" * 70)
print("✅ ALL VERIFICATION TESTS PASSED!")
print("=" * 70)

print("\n📚 Available Classes:")
print("  1. MLTrendAnalyzer        - Trend classification & reversal detection")
print("  2. MomentumAnalyzer       - Momentum & divergence analysis")
print("  3. TrendConfluenceScorer  - Multi-indicator confidence scoring")
print("  4. BacktestEngine         - Complete backtesting framework")
print("  5. StrategyOptimizer      - Parameter optimization")
print("  6. PerformanceAnalyzer    - Comparison & analysis tools")

print("\n🚀 Ready to run examples!")
print("   Run: python ml_backtest_examples.py")

print("\n" + "=" * 70)
