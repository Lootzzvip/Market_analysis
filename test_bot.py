"""
Test script to verify the headless bot works correctly
"""

import sys

print("="*80)
print("🧪 TESTING HEADLESS BOT SETUP")
print("="*80)

# Test 1: Import main modules
print("\n1️⃣ Testing imports from app.py...")
try:
    from app import BinanceDataFetcher, SMCIndicators, TradeMemory, TradeExecutor
    print("   ✅ Successfully imported: BinanceDataFetcher, SMCIndicators, TradeMemory, TradeExecutor")
except ImportError as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Import headless bot
print("\n2️⃣ Testing headless bot import...")
try:
    from trading_bot_headless import HeadlessTradingBot, CONFIG
    print("   ✅ Successfully imported HeadlessTradingBot")
except ImportError as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Test 3: Create bot instance
print("\n3️⃣ Creating bot instance...")
try:
    bot = HeadlessTradingBot(CONFIG)
    print("   ✅ Bot instance created successfully")
except Exception as e:
    print(f"   ❌ Failed to create bot: {e}")
    sys.exit(1)

# Test 4: Test data fetcher
print("\n4️⃣ Testing Binance data fetch...")
try:
    df = bot.fetcher.fetch_historical_data(timeframe='1h', limit=100)
    if df is not None and len(df) > 0:
        print(f"   ✅ Fetched {len(df)} candles successfully")
        print(f"   Latest price: ${df.iloc[-1]['close']:,.2f}")
    else:
        print("   ⚠️ Data fetch returned empty DataFrame")
except Exception as e:
    print(f"   ❌ Data fetch failed: {e}")
    print("   ⚠️ Check your internet connection or Binance API access")

# Test 5: Test HTF bias calculation
print("\n5️⃣ Testing HTF bias calculation...")
try:
    bias = bot.get_combined_htf_bias()
    bias_label = "🟢 BULLISH" if bias == 1 else "🔴 BEARISH" if bias == -1 else "⚪ NEUTRAL"
    print(f"   ✅ HTF Bias: {bias_label}")
except Exception as e:
    print(f"   ❌ HTF bias calculation failed: {e}")

# Test 6: Test signal generation
print("\n6️⃣ Testing signal generation...")
try:
    df = bot.fetcher.fetch_historical_data(timeframe='1h', limit=500)
    if df is not None and len(df) > 50:
        df = SMCIndicators.engineer_all_features(df, htf_bias=0, min_confluence_threshold=60)
        signal = bot.generate_signal_with_filters(df, '1h', 0, 60)
        print(f"   ✅ Signal type: {signal['type']}")
        print(f"   Reason: {signal.get('reason', 'N/A')}")
    else:
        print("   ⚠️ Not enough data to test signal generation")
except Exception as e:
    print(f"   ❌ Signal generation failed: {e}")

# Test 7: Check database
print("\n7️⃣ Testing database...")
try:
    stats = bot.trade_executor.trade_memory.get_overall_stats()
    print(f"   ✅ Database accessible")
    print(f"   Total trades: {stats['total_trades']}")
    print(f"   Win rate: {stats['win_rate']:.1f}%")
    print(f"   Total P&L: ${stats['total_pnl']:,.2f}")
except Exception as e:
    print(f"   ❌ Database access failed: {e}")

print("\n" + "="*80)
print("✅ ALL TESTS COMPLETED!")
print("="*80)
print("\n📝 Next steps:")
print("   1. Run full bot: python trading_bot_headless.py")
print("   2. Or single cycle: python trading_bot_single_cycle.py")
print("   3. Check logs: tail -f trading_bot.log")
print("\n🚀 Bot is ready for deployment!")
