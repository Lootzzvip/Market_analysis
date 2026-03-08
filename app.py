import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import time
import sqlite3
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import warnings
import os
os.environ['STREAMLIT_CLIENT_LOGGER_LEVEL'] = 'error'
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')

# Detect if running in Streamlit context
_STREAMLIT_RUNNING = False
try:
    # This will work only when running `streamlit run app.py`
    _STREAMLIT_RUNNING = bool(st.runtime.exists())
except:
    _STREAMLIT_RUNNING = False

# Warm cream / light-brown visual theme tokens.
THEME_BG = '#f6efe4'
THEME_CARD = '#fff9f0'
THEME_TEXT = '#4f3c2b'
THEME_GRID = '#d9c7ad'
THEME_BORDER = '#ceb79a'
THEME_ACCENT = '#b18457'


@st.cache_data(ttl=90, show_spinner=False)
def _fetch_ohlcv_cached(symbol, timeframe, limit):
    """Cached OHLCV fetch to reduce API pressure and UI lag on reruns."""
    import time
    
    # Retry configuration
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            exchange = ccxt.binance({
                'enableRateLimit': True,
                'timeout': 30000,  # 30 second timeout
                'options': {
                    'defaultType': 'spot',
                }
            })
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=int(limit))
            df_cached = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_cached['timestamp'] = pd.to_datetime(df_cached['timestamp'], unit='ms')
            return df_cached.sort_values('timestamp').reset_index(drop=True)
        
        except ccxt.NetworkError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            else:
                raise Exception(f"Network error after {max_retries} attempts: {str(e)}")
        
        except ccxt.ExchangeError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                raise Exception(f"Binance API error: {str(e)}")
        
        except Exception as e:
            raise Exception(f"Unexpected error fetching data: {str(e)}")

# ============================================================================
# MODULE 1: DATA ACQUISITION (CONTINUOUS LOOP)
# ============================================================================

class BinanceDataFetcher:
    """Fetch live OHLCV data from Binance via CCXT"""
    
    def __init__(self):
        self.exchange = ccxt.binance()
        self.symbol = 'BTC/USDT'
        
    def fetch_historical_data(self, timeframe='15m', limit=1000):
        """Fetch last N candles of historical data for given timeframe"""
        try:
            return _fetch_ohlcv_cached(self.symbol, timeframe, int(limit)).copy()
        except Exception as e:
            error_msg = str(e)
            try:
                if "Network error" in error_msg:
                    st.error(f"🌐 **Network Error ({timeframe}):** Unable to connect to Binance. Check your internet or use a VPN.")
                elif "API error" in error_msg or "Exchange" in error_msg:
                    st.error(f"⚠️ **Binance API Error ({timeframe}):** {error_msg}")
                else:
                    st.error(f"❌ **Error fetching {timeframe} data:** {error_msg}")
            except:
                print(f"Error fetching {timeframe} data: {error_msg}")
            return None

# ============================================================================
# MODULE 2: SMC FEATURE ENGINEERING (SMART MONEY CONCEPTS)
# ============================================================================

class SMCIndicators:
    """Calculate Smart Money Concepts features"""
    
    @staticmethod
    def calculate_swing_points(df, window=5):
        """Identify pivot-based swing highs/lows (fractal style) for cleaner structure."""
        left_right = max(2, window // 2)
        df['is_swing_high'] = False
        df['is_swing_low'] = False
        df['swing_high'] = np.nan
        df['swing_low'] = np.nan
        df['swing_high_strength'] = 0.0
        df['swing_low_strength'] = 0.0

        for i in range(left_right, len(df) - left_right):
            high_slice = df['high'].iloc[i - left_right:i + left_right + 1]
            low_slice = df['low'].iloc[i - left_right:i + left_right + 1]
            current_high = df.loc[i, 'high']
            current_low = df.loc[i, 'low']

            if current_high == high_slice.max() and (high_slice == current_high).sum() == 1:
                df.loc[i, 'is_swing_high'] = True
                df.loc[i, 'swing_high'] = current_high
                # Calculate strength based on distance from window extremes
                strength = (current_high - low_slice.min()) / df.loc[i, 'close']
                df.loc[i, 'swing_high_strength'] = strength

            if current_low == low_slice.min() and (low_slice == current_low).sum() == 1:
                df.loc[i, 'is_swing_low'] = True
                df.loc[i, 'swing_low'] = current_low
                # Calculate strength based on distance from window extremes
                strength = (high_slice.max() - current_low) / df.loc[i, 'close']
                df.loc[i, 'swing_low_strength'] = strength

        return df
    
    @staticmethod
    def calculate_fair_value_gaps(df, min_body_pct=0.15, min_gap_pct=0.03):
        """
        Fair Value Gaps (FVG) identification
        Bullish FVG: Candle1.High < Candle3.Low (gap up)
        Bearish FVG: Candle1.Low > Candle3.High (gap down)
        """
        df['fvg_bullish'] = False
        df['fvg_bearish'] = False
        df['fvg_type'] = 'none'
        df['fvg_size'] = 0.0
        df['fvg_lower'] = np.nan
        df['fvg_upper'] = np.nan
        avg_body = (df['close'] - df['open']).abs().rolling(20).mean().shift(1)
        
        for i in range(2, len(df)):
            first_high = df.loc[i-2, 'high']
            first_low = df.loc[i-2, 'low']
            third_low = df.loc[i, 'low']
            third_high = df.loc[i, 'high']

            mid_open = df.loc[i-1, 'open']
            mid_close = df.loc[i-1, 'close']
            mid_body_pct = (abs(mid_close - mid_open) / mid_open) * 100 if mid_open else 0
            mid_body = abs(mid_close - mid_open)
            body_threshold = avg_body.iloc[i] if pd.notna(avg_body.iloc[i]) else 0
            bullish_impulse = (mid_close > mid_open) and (mid_body_pct >= min_body_pct) and (mid_body >= body_threshold)
            bearish_impulse = (mid_close < mid_open) and (mid_body_pct >= min_body_pct) and (mid_body >= body_threshold)

            bullish_gap_size = third_low - first_high
            bearish_gap_size = first_low - third_high
            min_gap_abs = df.loc[i, 'close'] * (min_gap_pct / 100)

            bullish_gap = bullish_gap_size > min_gap_abs
            bearish_gap = bearish_gap_size > min_gap_abs

            # Exclusive classification to avoid conflicting labels
            if bullish_gap and bullish_impulse and (df.loc[i, 'close'] >= first_high):
                df.loc[i, 'fvg_bullish'] = True
                df.loc[i, 'fvg_type'] = 'bullish'
                df.loc[i, 'fvg_size'] = bullish_gap_size
                df.loc[i, 'fvg_lower'] = first_high
                df.loc[i, 'fvg_upper'] = third_low
            elif bearish_gap and bearish_impulse and (df.loc[i, 'close'] <= first_low):
                df.loc[i, 'fvg_bearish'] = True
                df.loc[i, 'fvg_type'] = 'bearish'
                df.loc[i, 'fvg_size'] = bearish_gap_size
                df.loc[i, 'fvg_lower'] = third_high
                df.loc[i, 'fvg_upper'] = first_low
        
        return df
    
    @staticmethod
    def calculate_bos_choch(df):
        """State-aware BOS/ChoCh using last confirmed swing pivots."""
        df['bos_bullish'] = False
        df['bos_bearish'] = False
        df['choch_bullish'] = False
        df['choch_bearish'] = False
        df['structure_state'] = 0

        last_swing_high = np.nan
        last_swing_low = np.nan
        state = 0
        
        for i in range(1, len(df)):
            if bool(df.loc[i - 1, 'is_swing_high']):
                last_swing_high = df.loc[i - 1, 'high']
            if bool(df.loc[i - 1, 'is_swing_low']):
                last_swing_low = df.loc[i - 1, 'low']

            close_now = df.loc[i, 'close']
            close_prev = df.loc[i - 1, 'close']

            if pd.notna(last_swing_high) and close_now > last_swing_high and close_prev <= last_swing_high:
                if state == -1:
                    df.loc[i, 'choch_bullish'] = True
                else:
                    df.loc[i, 'bos_bullish'] = True
                state = 1

            if pd.notna(last_swing_low) and close_now < last_swing_low and close_prev >= last_swing_low:
                if state == 1:
                    df.loc[i, 'choch_bearish'] = True
                else:
                    df.loc[i, 'bos_bearish'] = True
                state = -1

            df.loc[i, 'structure_state'] = state
        
        return df
    
    @staticmethod
    def calculate_rsi(df, period=14):
        """Calculate 14-period Relative Strength Index"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50)
        return df
    
    @staticmethod
    def calculate_volume_ma(df, period=20):
        """Calculate Volume Moving Average"""
        df['volume_ma'] = df['volume'].rolling(window=period).mean()
        return df
    
    @staticmethod
    def add_time_of_day(df):
        """Add hour of day feature for pattern recognition"""
        df['hour'] = df['timestamp'].dt.hour
        return df
    
    @staticmethod
    def calculate_support_resistance(df, window=20):
        """Support/resistance from most recent confirmed swing pivots."""
        df['swing_low_level'] = df['low'].where(df['is_swing_low'])
        df['swing_high_level'] = df['high'].where(df['is_swing_high'])

        df['support'] = df['swing_low_level'].ffill().shift(1)
        df['resistance'] = df['swing_high_level'].ffill().shift(1)

        zone_width = np.where(
            pd.notna(df.get('atr', np.nan)),
            df.get('atr', pd.Series(np.nan, index=df.index)) * 0.20,
            df['close'] * 0.0018,
        )
        zone_width = pd.Series(zone_width, index=df.index).fillna(df['close'] * 0.0018)
        df['support_zone_low'] = df['support'] - zone_width
        df['support_zone_high'] = df['support'] + zone_width
        df['resistance_zone_low'] = df['resistance'] - zone_width
        df['resistance_zone_high'] = df['resistance'] + zone_width
        return df

    @staticmethod
    def calculate_trend_features(df):
        """Trend regime and momentum features for ML"""
        df['ema_fast'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_trend'] = (df['ema_fast'] - df['ema_slow']) / df['close'].replace(0, np.nan)
        df['trend_slope_10'] = df['close'].pct_change(10)
        df['trend_slope_20'] = df['close'].pct_change(20)
        df['trend_volatility_20'] = df['close'].pct_change().rolling(20).std()
        df['market_trend'] = np.where(df['ema_fast'] > df['ema_slow'], 1, -1)
        return df

    @staticmethod
    def calculate_atr_adx(df, period=14):
        """ATR and ADX regime filters."""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(period).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100

        up_move = df['high'].diff()
        down_move = -df['low'].diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr_smooth = true_range.rolling(period).sum().replace(0, np.nan)
        plus_di = 100 * (pd.Series(plus_dm).rolling(period).sum() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm).rolling(period).sum() / tr_smooth)
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
        df['adx'] = dx.rolling(period).mean().fillna(0)
        return df

    @staticmethod
    def calculate_liquidity_sweep_and_displacement(df, sweep_window=12):
        """Liquidity sweep + displacement strength near FVG formation."""
        prev_high = df['high'].shift(2).rolling(sweep_window).max()
        prev_low = df['low'].shift(2).rolling(sweep_window).min()

        df['sweep_high'] = df['high'].shift(1) > prev_high
        df['sweep_low'] = df['low'].shift(1) < prev_low

        mid_open = df['open'].shift(1)
        mid_close = df['close'].shift(1)
        df['displacement_pct'] = ((mid_close - mid_open).abs() / mid_open.replace(0, np.nan)) * 100
        df['displacement_direction'] = np.where(mid_close > mid_open, 1, -1)
        return df

    @staticmethod
    def calculate_premium_discount_context(df, lookback=50):
        """Premium/discount zone relative to rolling equilibrium."""
        range_high = df['high'].rolling(lookback).max()
        range_low = df['low'].rolling(lookback).min()
        df['eq_mid'] = (range_high + range_low) / 2
        df['in_discount'] = df['close'] < df['eq_mid']
        df['in_premium'] = df['close'] > df['eq_mid']
        return df

    @staticmethod
    def calculate_order_blocks(df, impulse_threshold=0.4):
        """
        Order Block detection using swing structures
        Bullish OB: Last bearish candle before breaking above swing high
        Bearish OB: Last bullish candle before breaking below swing low
        """
        df['ob_bullish'] = False
        df['ob_bearish'] = False
        df['ob_type'] = 'none'
        df['ob_high'] = np.nan
        df['ob_low'] = np.nan
        df['ob_strength'] = 0.0
        
        # Identify the last swing high and swing low
        last_swing_high_idx = -1
        last_swing_high_price = -1
        last_swing_low_idx = -1
        last_swing_low_price = float('inf')
        
        for i in range(len(df)):
            # Track swing highs
            if bool(df.loc[i, 'is_swing_high']):
                last_swing_high_idx = i
                last_swing_high_price = df.loc[i, 'high']
            
            # Track swing lows
            if bool(df.loc[i, 'is_swing_low']):
                last_swing_low_idx = i
                last_swing_low_price = df.loc[i, 'low']
        
        # Now detect order blocks based on swing breaks
        for i in range(2, len(df)):
            curr_close = df.loc[i, 'close']
            prev_close = df.loc[i-1, 'close']
            curr_open = df.loc[i, 'open']
            curr_close_price = df.loc[i, 'close']
            
            # Bullish Order Block: Price breaks above last swing high
            if (last_swing_high_idx >= 0 and i > last_swing_high_idx + 2 and 
                prev_close <= last_swing_high_price and curr_close > last_swing_high_price):
                
                # Find the last bearish candle before this break
                for lookback in range(1, min(8, i - last_swing_high_idx)):
                    idx = i - lookback
                    if df.loc[idx, 'close'] < df.loc[idx, 'open']:
                        df.loc[idx, 'ob_bullish'] = True
                        df.loc[idx, 'ob_type'] = 'bullish'
                        df.loc[idx, 'ob_high'] = df.loc[idx, 'high']
                        df.loc[idx, 'ob_low'] = df.loc[idx, 'low']
                        body_size = abs(df.loc[idx, 'close'] - df.loc[idx, 'open'])
                        df.loc[idx, 'ob_strength'] = (body_size / df.loc[idx, 'open']) * 100
                        break
            
            # Bearish Order Block: Price breaks below last swing low
            if (last_swing_low_idx >= 0 and i > last_swing_low_idx + 2 and 
                prev_close >= last_swing_low_price and curr_close < last_swing_low_price):
                
                # Find the last bullish candle before this break
                for lookback in range(1, min(8, i - last_swing_low_idx)):
                    idx = i - lookback
                    if df.loc[idx, 'close'] > df.loc[idx, 'open']:
                        df.loc[idx, 'ob_bearish'] = True
                        df.loc[idx, 'ob_type'] = 'bearish'
                        df.loc[idx, 'ob_high'] = df.loc[idx, 'high']
                        df.loc[idx, 'ob_low'] = df.loc[idx, 'low']
                        body_size = abs(df.loc[idx, 'close'] - df.loc[idx, 'open'])
                        df.loc[idx, 'ob_strength'] = (body_size / df.loc[idx, 'open']) * 100
                        break
        
        return df

    @staticmethod
    def calculate_fvg_validity(df):
        """Invalidate FVGs that are too close to opposite liquidity walls."""
        df['distance_to_resistance_pct'] = ((df['resistance'] - df['close']) / df['close']) * 100
        df['distance_to_support_pct'] = ((df['close'] - df['support']) / df['close']) * 100
        df['fvg_valid'] = False
        df['fvg_confluence_score'] = 0.0
        df['fvg_invalid_reason'] = ''

        for i in range(len(df)):
            if not (df.loc[i, 'fvg_bullish'] or df.loc[i, 'fvg_bearish']):
                continue

            close_price = df.loc[i, 'close']
            fvg_size_pct = (df.loc[i, 'fvg_size'] / close_price) * 100 if close_price > 0 else 0
            min_space_pct = max(0.35, fvg_size_pct * 1.2)
            score = 0

            if bool(df.loc[i, 'regime_ok']):
                score += 15
            if bool(df.loc[i, 'adx_ok']):
                score += 15
            if float(df.loc[i, 'displacement_pct'] if pd.notna(df.loc[i, 'displacement_pct']) else 0) >= 0.20:
                score += 20

            if df.loc[i, 'fvg_bullish']:
                dist_res = df.loc[i, 'distance_to_resistance_pct']
                if bool(df.loc[i, 'sweep_low']):
                    score += 20
                if bool(df.loc[i, 'in_discount']):
                    score += 10
                if int(df.loc[i, 'htf_bias']) == 1:
                    score += 20
                if pd.isna(dist_res) or dist_res <= 0:
                    df.loc[i, 'fvg_valid'] = False
                    df.loc[i, 'fvg_invalid_reason'] = 'No clean resistance distance'
                elif dist_res < min_space_pct:
                    df.loc[i, 'fvg_valid'] = False
                    df.loc[i, 'fvg_invalid_reason'] = 'Resistance too close'
                else:
                    df.loc[i, 'fvg_valid'] = score >= float(df.loc[i, 'min_confluence_threshold'])
                    if not df.loc[i, 'fvg_valid']:
                        df.loc[i, 'fvg_invalid_reason'] = 'Low confluence score'

            if df.loc[i, 'fvg_bearish']:
                dist_sup = df.loc[i, 'distance_to_support_pct']
                if bool(df.loc[i, 'sweep_high']):
                    score += 20
                if bool(df.loc[i, 'in_premium']):
                    score += 10
                if int(df.loc[i, 'htf_bias']) == -1:
                    score += 20
                if pd.isna(dist_sup) or dist_sup <= 0:
                    df.loc[i, 'fvg_valid'] = False
                    df.loc[i, 'fvg_invalid_reason'] = 'No clean support distance'
                elif dist_sup < min_space_pct:
                    df.loc[i, 'fvg_valid'] = False
                    df.loc[i, 'fvg_invalid_reason'] = 'Support too close'
                else:
                    df.loc[i, 'fvg_valid'] = score >= float(df.loc[i, 'min_confluence_threshold'])
                    if not df.loc[i, 'fvg_valid']:
                        df.loc[i, 'fvg_invalid_reason'] = 'Low confluence score'

            df.loc[i, 'fvg_confluence_score'] = score
        return df
    
    @staticmethod
    def get_mtf_support_resistance(fetcher):
        """Get multi-timeframe support/resistance zones (1w -> 1d -> 4h -> 2h -> 1h)"""
        mtf_zones = []
        
        # Define timeframes in order of strength (highest to lowest)
        timeframes = [
            ('1w', 'Weekly', '#FF1493', 0.35, 3.5, 3),      # Magenta, strongest
            ('1d', 'Daily', '#9370DB', 0.28, 3.0, 3),       # Medium purple
            ('4h', '4-Hour', '#BA55D3', 0.22, 2.5, 4),      # Light purple
            ('2h', '2-Hour', '#DDA0DD', 0.18, 2.0, 4),      # Plum
            ('1h', '1-Hour', '#E6E6FA', 0.14, 1.5, 5),      # Lavender
        ]
        
        for tf, tf_name, color, opacity, line_width, top_n in timeframes:
            try:
                # Fetch data for this timeframe
                df_tf = fetcher.fetch_historical_data(timeframe=tf, limit=200)
                if df_tf is None or len(df_tf) < 20:
                    continue
                
                # Calculate swing points and ATR
                df_tf = SMCIndicators.calculate_swing_points(df_tf)
                df_tf = SMCIndicators.calculate_atr_adx(df_tf)
                
                # Get strongest support zones
                swing_lows = df_tf[df_tf['is_swing_low']].copy()
                if len(swing_lows) > 0:
                    recent_lows = swing_lows.tail(12).nlargest(min(top_n, len(swing_lows)), 'swing_low_strength')
                    for idx, row in recent_lows.iterrows():
                        zone_half = (row['atr'] * 0.30) if pd.notna(row.get('atr')) and row.get('atr', 0) > 0 else row['close'] * 0.0025
                        mtf_zones.append({
                            'type': 'support',
                            'timeframe': tf_name,
                            'price': row['low'],
                            'zone_low': row['low'] - zone_half,
                            'zone_high': row['low'] + zone_half,
                            'timestamp': row['timestamp'],
                            'color': color,
                            'opacity': opacity,
                            'line_width': line_width,
                            'strength': row['swing_low_strength']
                        })
                
                # Get strongest resistance zones
                swing_highs = df_tf[df_tf['is_swing_high']].copy()
                if len(swing_highs) > 0:
                    recent_highs = swing_highs.tail(12).nlargest(min(top_n, len(swing_highs)), 'swing_high_strength')
                    for idx, row in recent_highs.iterrows():
                        zone_half = (row['atr'] * 0.30) if pd.notna(row.get('atr')) and row.get('atr', 0) > 0 else row['close'] * 0.0025
                        mtf_zones.append({
                            'type': 'resistance',
                            'timeframe': tf_name,
                            'price': row['high'],
                            'zone_low': row['high'] - zone_half,
                            'zone_high': row['high'] + zone_half,
                            'timestamp': row['timestamp'],
                            'color': color,
                            'opacity': opacity,
                            'line_width': line_width,
                            'strength': row['swing_high_strength']
                        })
            except Exception as e:
                try:
                    st.warning(f"Could not fetch {tf_name} zones: {e}")
                except:
                    print(f"Could not fetch {tf_name} zones: {e}")
                continue
        
        return mtf_zones
    
    @classmethod
    def engineer_all_features(cls, df, htf_bias=0, min_confluence_threshold=60):
        """Apply all SMC features to dataframe"""
        df = cls.calculate_swing_points(df)
        df = cls.calculate_fair_value_gaps(df)
        df = cls.calculate_bos_choch(df)
        df = cls.calculate_rsi(df)
        df = cls.calculate_volume_ma(df)
        df = cls.add_time_of_day(df)
        df = cls.calculate_trend_features(df)
        df = cls.calculate_atr_adx(df)
        df = cls.calculate_support_resistance(df)
        df = cls.calculate_liquidity_sweep_and_displacement(df)
        df = cls.calculate_premium_discount_context(df)
        df = cls.calculate_order_blocks(df)
        df['htf_bias'] = int(htf_bias)
        df['regime_ok'] = df['atr_pct'] > 0.25
        df['adx_ok'] = df['adx'] > 18
        df['min_confluence_threshold'] = float(min_confluence_threshold)
        df = cls.calculate_fvg_validity(df)
        return df


class TrendMLDatabase:
    """Persistent trend/FVG training memory for improving ML over time."""

    def __init__(self, db_path='trend_ml_data_v3.db'):
        self.db_path = db_path
        self._initialize()

    def _initialize(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fvg_training_samples (
                timestamp TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction INTEGER NOT NULL,
                fvg_size REAL,
                rsi REAL,
                hour INTEGER,
                volume REAL,
                ema_trend REAL,
                trend_slope_10 REAL,
                trend_slope_20 REAL,
                trend_volatility_20 REAL,
                atr_pct REAL,
                adx REAL,
                htf_bias INTEGER,
                displacement_pct REAL,
                sweep_high INTEGER,
                sweep_low INTEGER,
                in_premium INTEGER,
                in_discount INTEGER,
                fvg_confluence_score REAL,
                distance_to_resistance_pct REAL,
                distance_to_support_pct REAL,
                fvg_valid INTEGER,
                target INTEGER,
                PRIMARY KEY (timestamp, timeframe)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_snapshots (
                snapshot_time TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                close REAL,
                rsi REAL,
                volume REAL,
                ema_trend REAL,
                atr_pct REAL,
                adx REAL,
                htf_bias INTEGER,
                market_trend INTEGER,
                latest_fvg_valid INTEGER,
                latest_confluence_score REAL,
                latest_fvg_probability REAL
            )
            """
        )
        conn.commit()
        conn.close()

    def upsert_training_samples(self, samples_df, timeframe):
        if samples_df.empty:
            return
        records = []
        for _, row in samples_df.iterrows():
            direction = 1 if row.get('fvg_type', 'none') == 'bullish' else -1
            records.append((
                row['timestamp'].isoformat(),
                timeframe,
                direction,
                float(row.get('fvg_size', 0) or 0),
                float(row.get('rsi', 0) or 0),
                int(row.get('hour', 0) or 0),
                float(row.get('volume', 0) or 0),
                float(row.get('ema_trend', 0) or 0),
                float(row.get('trend_slope_10', 0) or 0),
                float(row.get('trend_slope_20', 0) or 0),
                float(row.get('trend_volatility_20', 0) or 0),
                float(row.get('atr_pct', 0) or 0),
                float(row.get('adx', 0) or 0),
                int(row.get('htf_bias', 0) or 0),
                float(row.get('displacement_pct', 0) or 0),
                int(bool(row.get('sweep_high', False))),
                int(bool(row.get('sweep_low', False))),
                int(bool(row.get('in_premium', False))),
                int(bool(row.get('in_discount', False))),
                float(row.get('fvg_confluence_score', 0) or 0),
                float(row.get('distance_to_resistance_pct', 0) or 0),
                float(row.get('distance_to_support_pct', 0) or 0),
                int(bool(row.get('fvg_valid', False))),
                int(row.get('target', 0) or 0),
            ))

        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            """
            INSERT OR REPLACE INTO fvg_training_samples (
                timestamp, timeframe, direction, fvg_size, rsi, hour, volume,
                ema_trend, trend_slope_10, trend_slope_20, trend_volatility_20,
                atr_pct, adx, htf_bias, displacement_pct, sweep_high, sweep_low,
                in_premium, in_discount, fvg_confluence_score,
                distance_to_resistance_pct, distance_to_support_pct, fvg_valid, target
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records
        )
        conn.commit()
        conn.close()

    def load_training_samples(self):
        conn = sqlite3.connect(self.db_path)
        df_db = pd.read_sql_query("SELECT * FROM fvg_training_samples", conn)
        conn.close()
        return df_db

    def log_trend_snapshot(self, latest_row, timeframe, latest_prob):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO trend_snapshots (
                snapshot_time, timeframe, close, rsi, volume, ema_trend,
                atr_pct, adx, htf_bias, market_trend, latest_fvg_valid,
                latest_confluence_score, latest_fvg_probability
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                timeframe,
                float(latest_row.get('close', 0) or 0),
                float(latest_row.get('rsi', 0) or 0),
                float(latest_row.get('volume', 0) or 0),
                float(latest_row.get('ema_trend', 0) or 0),
                float(latest_row.get('atr_pct', 0) or 0),
                float(latest_row.get('adx', 0) or 0),
                int(latest_row.get('htf_bias', 0) or 0),
                int(latest_row.get('market_trend', 0) or 0),
                int(bool(latest_row.get('fvg_valid', False))),
                float(latest_row.get('fvg_confluence_score', 0) or 0),
                None if latest_prob is None else float(latest_prob),
            )
        )
        conn.commit()
        conn.close()

# ============================================================================
# MODULE 3: TRADING SYSTEM (TRADE EXECUTOR & LEARNING MEMORY)
# ============================================================================

class TradeMemory:
    """Track trades and improve strategy based on results"""
    
    def __init__(self, db_path='trade_history_v1.db'):
        self.db_path = db_path
        self._initialize()

    def _connect(self):
        """Create resilient sqlite connection for frequent read/write cycles."""
        return sqlite3.connect(self.db_path, timeout=30)
    
    def _initialize(self):
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timeframe TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                risk REAL NOT NULL,
                reward REAL NOT NULL,
                direction TEXT,
                entry_reason TEXT,
                exit_time TEXT,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                result TEXT,
                close_reason TEXT,
                close_confidence REAL,
                close_explanation TEXT,
                confluence_score REAL,
                rsi_at_entry REAL,
                htf_bias INTEGER,
                fvg_type TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_stats (
                timeframe TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0.0,
                avg_win REAL DEFAULT 0.0,
                avg_loss REAL DEFAULT 0.0,
                profit_factor REAL DEFAULT 0.0,
                total_pnl REAL DEFAULT 0.0,
                last_updated TEXT
            )
            """
        )

        # Backward-compatible schema upgrades for existing DBs.
        schema_additions = [
            ("direction", "TEXT"),
            ("entry_reason", "TEXT"),
            ("close_reason", "TEXT"),
            ("close_confidence", "REAL"),
            ("close_explanation", "TEXT"),
        ]
        for col, col_type in schema_additions:
            try:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                # Column already exists.
                pass

        conn.commit()
        conn.close()
    
    def log_trade(self, timeframe, entry_price, stop_loss, take_profit,
                  confluence_score, rsi, htf_bias, fvg_type,
                  direction=None, entry_reason=''):
        """Log a new trade entry"""
        conn = self._connect()
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        if direction is None:
            direction = 'BUY' if take_profit > entry_price else 'SELL'
        
        conn.execute(
            """
            INSERT INTO trades (timeframe, entry_time, entry_price, stop_loss, 
                              take_profit, risk, reward, confluence_score, 
                              rsi_at_entry, htf_bias, fvg_type, direction, entry_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timeframe,
                datetime.now().isoformat(),
                float(entry_price),
                float(stop_loss),
                float(take_profit),
                float(risk),
                float(reward),
                float(confluence_score),
                float(rsi),
                int(htf_bias),
                fvg_type,
                direction,
                entry_reason,
                datetime.now().isoformat()
            )
        )
        conn.commit()
        last_trade_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return last_trade_id
    
    def close_trade(self, trade_id, exit_price):
        """Close a trade and record results"""
        conn = self._connect()
        timeframe_to_update = None
        
        trade = conn.execute(
            """
            SELECT entry_price, stop_loss, take_profit, risk, reward, timeframe,
                   direction, confluence_score, rsi_at_entry, htf_bias, fvg_type, entry_reason
            FROM trades WHERE trade_id = ?
            """,
            (trade_id,)
        ).fetchone()
        
        if trade:
            (
                entry_price, stop_loss, take_profit, risk, reward, timeframe,
                direction, confluence_score, rsi_at_entry, htf_bias, fvg_type, entry_reason
            ) = trade

            if not direction:
                direction = 'BUY' if take_profit > entry_price else 'SELL'

            pnl = (exit_price - entry_price) if direction == 'BUY' else (entry_price - exit_price)
            pnl_pct = (pnl / entry_price) * 100 if entry_price != 0 else 0
            
            # Determine result (direction-aware).
            if direction == 'BUY':
                if exit_price >= take_profit:
                    result = 'WIN'
                    close_reason = 'Take Profit Hit'
                elif exit_price <= stop_loss:
                    result = 'LOSS'
                    close_reason = 'Stop Loss Hit'
                else:
                    result = 'CLOSED'
                    close_reason = 'Manual/Other Close'
            else:
                if exit_price <= take_profit:
                    result = 'WIN'
                    close_reason = 'Take Profit Hit'
                elif exit_price >= stop_loss:
                    result = 'LOSS'
                    close_reason = 'Stop Loss Hit'
                else:
                    result = 'CLOSED'
                    close_reason = 'Manual/Other Close'

            # Build a professional confidence and explanation summary.
            conf = float(confluence_score or 0)
            rsi = float(rsi_at_entry or 50)
            bias = int(htf_bias or 0)
            direction_bias_aligned = (direction == 'BUY' and bias >= 0) or (direction == 'SELL' and bias <= 0)
            rsi_aligned = (direction == 'BUY' and rsi < 60) or (direction == 'SELL' and rsi > 40)
            confidence_score = conf
            confidence_score += 8 if direction_bias_aligned else -8
            confidence_score += 5 if rsi_aligned else -5
            confidence_score = max(0.0, min(100.0, confidence_score))

            rr = abs((take_profit - entry_price) / (entry_price - stop_loss)) if (entry_price - stop_loss) != 0 else 0
            explanation = (
                f"Outcome: {result}. Trigger: {close_reason}. "
                f"Direction: {direction}. Entry reason: {entry_reason or 'SMC/FVG signal'}. "
                f"Confluence={conf:.0f}, RSI={rsi:.1f}, HTF bias={bias}, "
                f"Bias alignment={'Yes' if direction_bias_aligned else 'No'}, "
                f"RSI alignment={'Yes' if rsi_aligned else 'No'}, "
                f"Planned RR~{rr:.2f}."
            )
            
            conn.execute(
                """
                UPDATE trades 
                SET exit_time = ?, exit_price = ?, pnl = ?, pnl_pct = ?, result = ?,
                    close_reason = ?, close_confidence = ?, close_explanation = ?
                WHERE trade_id = ?
                """,
                (datetime.now().isoformat(), float(exit_price), float(pnl), 
                 float(pnl_pct), result, close_reason, float(confidence_score), explanation, trade_id)
            )
            timeframe_to_update = timeframe
        
        conn.commit()
        conn.close()

        # Run stats update in a separate connection after write lock is released.
        if timeframe_to_update:
            self._update_stats(timeframe_to_update)
    
    def _update_stats(self, timeframe):
        """Update trade statistics for a timeframe"""
        conn = self._connect()
        
        stats = conn.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN result = 'WIN' THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN result = 'LOSS' THEN pnl ELSE NULL END) as avg_loss,
                SUM(pnl) as total_pnl
            FROM trades
            WHERE timeframe = ? AND result IS NOT NULL
            """,
            (timeframe,)
        ).fetchone()
        
        if stats:
            total, wins, losses, avg_win, avg_loss, total_pnl = stats
            wins = wins or 0
            losses = losses or 0
            avg_win = avg_win or 0.0
            avg_loss = abs(avg_loss) if avg_loss else 0.0
            total_pnl = total_pnl or 0.0
            
            win_rate = (wins / total * 100) if total > 0 else 0.0
            profit_factor = (avg_win / avg_loss) if avg_loss > 0 else 0.0 if avg_win == 0 else float('inf')
            
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_stats 
                (timeframe, total_trades, winning_trades, losing_trades, win_rate, 
                 avg_win, avg_loss, profit_factor, total_pnl, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (timeframe, total, wins, losses, win_rate, avg_win, avg_loss, 
                 profit_factor, total_pnl, datetime.now().isoformat())
            )
        
        conn.commit()
        conn.close()
    
    def get_stats(self, timeframe):
        """Get trade stats for a timeframe"""
        conn = self._connect()
        stats = conn.execute(
            "SELECT total_trades, winning_trades, losing_trades, win_rate, avg_win, avg_loss, profit_factor, total_pnl FROM trade_stats WHERE timeframe = ?",
            (timeframe,)
        ).fetchone()
        conn.close()
        
        if stats:
            return {
                'total': stats[0],
                'wins': stats[1],
                'losses': stats[2],
                'win_rate': stats[3],
                'avg_win': stats[4],
                'avg_loss': stats[5],
                'profit_factor': stats[6],
                'total_pnl': stats[7]
            }
        return None
    
    def get_overall_stats(self):
        """Get overall trade stats across all timeframes"""
        conn = self._connect()
        result = conn.execute(
            """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN result = 'WIN' THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN result = 'LOSS' THEN pnl ELSE NULL END) as avg_loss,
                SUM(pnl) as total_pnl
            FROM trades WHERE result IS NOT NULL
            """
        ).fetchone()
        conn.close()
        
        if result and result[0] > 0:
            total = result[0]
            wins = result[1] or 0
            losses = result[2] or 0
            win_rate = (wins / total * 100) if total > 0 else 0
            profit_factor = abs(result[3] / result[4]) if result[4] and result[4] != 0 else 0
            
            return {
                'total_trades': total,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'avg_win': result[3] or 0,
                'avg_loss': result[4] or 0,
                'profit_factor': profit_factor,
                'total_pnl': result[5] or 0
            }
        
        return {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'total_pnl': 0
        }
    
    def clear_all_trades(self):
        """Clear all trades from database (for testing/reset)"""
        try:
            conn = self._connect()
            # Delete from tables that exist
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM trade_stats")
            
            # Try to delete from ML training tables if they exist
            try:
                conn.execute("DELETE FROM fvg_training_samples")
            except:
                pass  # Table might not exist
            
            try:
                conn.execute("DELETE FROM trend_snapshots")
            except:
                pass  # Table might not exist
                
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error clearing trades: {e}")
            return False
    
    def get_open_trades(self):
        """Get all open trades"""
        conn = self._connect()
        trades = conn.execute(
            """
            SELECT trade_id, timeframe, entry_time, entry_price, stop_loss, take_profit, 
                   risk, reward, confluence_score, rsi_at_entry, fvg_type, direction, entry_reason
            FROM trades WHERE result IS NULL
            ORDER BY entry_time DESC
            """
        ).fetchall()
        conn.close()
        return trades
    
    def get_recent_trades(self, limit=10):
        """Get recent closed trades"""
        conn = self._connect()
        trades = conn.execute(
            """
            SELECT trade_id, timeframe, entry_time, entry_price, stop_loss, take_profit,
                   exit_time, exit_price, pnl, pnl_pct, result
            FROM trades WHERE result IS NOT NULL
            ORDER BY exit_time DESC LIMIT ?
            """,
            (limit,)
        ).fetchall()
        conn.close()
        return trades

    def get_closed_trades_by_result(self, result, limit=25):
        """Get closed trades filtered by WIN/LOSS with professional outcome analysis fields."""
        conn = self._connect()
        trades = conn.execute(
            """
            SELECT trade_id, timeframe, entry_time, entry_price, stop_loss, take_profit,
                   exit_time, exit_price, pnl, pnl_pct, result,
                   COALESCE(direction, CASE WHEN take_profit > entry_price THEN 'BUY' ELSE 'SELL' END) as direction,
                   confluence_score, rsi_at_entry, htf_bias, fvg_type,
                   close_reason, close_confidence, close_explanation
            FROM trades
            WHERE result = ?
            ORDER BY exit_time DESC
            LIMIT ?
            """,
            (result, limit)
        ).fetchall()
        conn.close()
        return trades

    def should_avoid_similar_setup(self, timeframe, direction, fvg_type, rsi, confluence_score, htf_bias, cooldown_hours=72):
        """Return (block, reason) when recent loss pattern is too similar and confidence is not materially stronger."""
        conn = self._connect()
        recent_losses = conn.execute(
            """
            SELECT trade_id, entry_time, exit_time, confluence_score, rsi_at_entry, htf_bias,
                   fvg_type, COALESCE(direction, CASE WHEN take_profit > entry_price THEN 'BUY' ELSE 'SELL' END) as direction,
                   close_reason, pnl_pct
            FROM trades
            WHERE timeframe = ? AND result = 'LOSS'
            ORDER BY exit_time DESC
            LIMIT 30
            """,
            (timeframe,)
        ).fetchall()
        conn.close()

        if not recent_losses:
            return False, ""

        now = datetime.utcnow()
        for row in recent_losses:
            (
                trade_id, _entry_time, exit_time, loss_conf, loss_rsi, loss_bias,
                loss_fvg, loss_direction, close_reason, loss_pnl_pct
            ) = row

            if not exit_time:
                continue
            try:
                elapsed_hours = (now - datetime.fromisoformat(str(exit_time))).total_seconds() / 3600.0
            except Exception:
                continue

            if elapsed_hours > cooldown_hours:
                continue

            same_direction = (str(loss_direction) == str(direction))
            same_fvg = (str(loss_fvg) == str(fvg_type))
            same_bias = int(loss_bias or 0) == int(htf_bias or 0)
            close_rsi = abs(float(loss_rsi or 50) - float(rsi or 50)) <= 6
            close_conf = abs(float(loss_conf or 0) - float(confluence_score or 0)) <= 12

            if same_direction and same_fvg and same_bias and close_rsi and close_conf:
                # Only allow if present setup is materially stronger than the losing one.
                if float(confluence_score or 0) < float(loss_conf or 0) + 15:
                    reason = (
                        f"Blocked similar losing setup: trade #{trade_id} lost {loss_pnl_pct or 0:.2f}% "
                        f"({close_reason or 'Stop Loss Hit'}) {elapsed_hours:.1f}h ago. "
                        f"Need confluence >= {(float(loss_conf or 0) + 15):.0f} for re-entry."
                    )
                    return True, reason

        return False, ""

    def get_latest_loss_diagnosis(self, timeframe=None):
        """Provide latest loss with professional root-cause text (fallback for legacy rows without explanation)."""
        conn = self._connect()
        if timeframe:
            row = conn.execute(
                """
                SELECT trade_id, timeframe, entry_price, stop_loss, take_profit, exit_price, pnl_pct,
                       COALESCE(direction, CASE WHEN take_profit > entry_price THEN 'BUY' ELSE 'SELL' END) as direction,
                       confluence_score, rsi_at_entry, htf_bias, fvg_type,
                       close_reason, close_confidence, close_explanation, exit_time
                FROM trades
                WHERE result = 'LOSS' AND timeframe = ?
                ORDER BY exit_time DESC LIMIT 1
                """,
                (timeframe,)
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT trade_id, timeframe, entry_price, stop_loss, take_profit, exit_price, pnl_pct,
                       COALESCE(direction, CASE WHEN take_profit > entry_price THEN 'BUY' ELSE 'SELL' END) as direction,
                       confluence_score, rsi_at_entry, htf_bias, fvg_type,
                       close_reason, close_confidence, close_explanation, exit_time
                FROM trades
                WHERE result = 'LOSS'
                ORDER BY exit_time DESC LIMIT 1
                """
            ).fetchone()
        conn.close()

        if not row:
            return None

        (
            trade_id, tf, entry_price, stop_loss, take_profit, exit_price, pnl_pct,
            direction, confluence_score, rsi_at_entry, htf_bias, fvg_type,
            close_reason, close_confidence, close_explanation, exit_time
        ) = row

        if close_explanation:
            explanation = close_explanation
        else:
            # Fallback diagnosis for historical rows that predate explanation fields.
            explanation = (
                f"Legacy loss (trade #{trade_id}) closed at stop-loss. Likely weak edge for this setup: "
                f"direction={direction}, fvg_type={fvg_type}, confluence={float(confluence_score or 0):.0f}, "
                f"rsi={float(rsi_at_entry or 50):.1f}, htf_bias={int(htf_bias or 0)}."
            )

        return {
            'trade_id': int(trade_id),
            'timeframe': tf,
            'entry_price': float(entry_price),
            'stop_loss': float(stop_loss),
            'take_profit': float(take_profit),
            'exit_price': float(exit_price or 0),
            'pnl_pct': float(pnl_pct or 0),
            'direction': direction,
            'fvg_type': fvg_type,
            'confluence_score': float(confluence_score or 0),
            'rsi_at_entry': float(rsi_at_entry or 50),
            'htf_bias': int(htf_bias or 0),
            'close_reason': close_reason or 'Stop Loss Hit',
            'close_confidence': None if close_confidence is None else float(close_confidence),
            'close_explanation': explanation,
            'exit_time': exit_time,
        }


class TradeExecutor:
    """Execute trades based on FVG and SMC signals with 1:2 risk/reward"""
    
    def __init__(self, initial_balance=10000):
        self.balance = initial_balance
        self.equity = initial_balance
        self.open_trades = {}
        self.trade_memory = TradeMemory()
        self.sync_open_trades_from_db()

    def sync_open_trades_from_db(self):
        """Reload open trades from DB so trade tracking survives reruns/restarts."""
        db_open_trades = self.trade_memory.get_open_trades()
        synced = {}
        for trade in db_open_trades:
            (
                trade_id, timeframe, _entry_time, entry_price, stop_loss, take_profit,
                _risk_db, _reward_db, _confluence_score, _rsi, _fvg_type, direction, _entry_reason
            ) = trade

            inferred_direction = direction if direction in ('BUY', 'SELL') else ('BUY' if take_profit > entry_price else 'SELL')
            risk_abs = abs(entry_price - stop_loss)
            risk_per_trade = self.balance * 0.02
            position_size = (risk_per_trade / risk_abs) if risk_abs > 0 else 0.0
            signed_risk = risk_abs if inferred_direction == 'BUY' else -risk_abs

            synced[int(trade_id)] = {
                'timeframe': timeframe,
                'type': inferred_direction,
                'entry': float(entry_price),
                'stop_loss': float(stop_loss),
                'take_profit': float(take_profit),
                'position_size': float(position_size),
                'risk': float(signed_risk)
            }

        self.open_trades = synced
        return len(self.open_trades)
    
    def generate_signal(self, df, timeframe, confluenceThreshold=60):
        """
        Generate a trading signal based on SMC indicators with STRICT FILTERS to reduce losses
        Returns: {'type': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'tp': price, 'risk': value}
        """
        if len(df) < 5:
            return {'type': 'NONE', 'reason': 'Insufficient data'}
        
        latest = df.iloc[-1]
        
        # Get safety settings from session state (with defaults)
        safety_settings = st.session_state.get('safety_settings', {
            'enable_htf_filter': True,
            'enable_adx_filter': True,
            'enable_volume_filter': True,
            'min_win_rate_threshold': 35,
            'risk_reward_ratio': 3
        })
        
        # ========================================================================
        # SAFETY FILTER 1: Win Rate Circuit Breaker
        # Pause trading if recent win rate is too low
        # ========================================================================
        stats = self.trade_memory.get_overall_stats()
        if stats['total_trades'] >= 10:  # Need at least 10 trades to judge
            recent_win_rate = stats['win_rate']
            min_win_rate = safety_settings.get('min_win_rate_threshold', 35)
            if recent_win_rate < min_win_rate:
                return {
                    'type': 'NONE',
                    'reason': f'⛔ Trading paused - Win rate {recent_win_rate:.1f}% < {min_win_rate}%. Review strategy.',
                    'paused': True
                }
        
        # ========================================================================
        # SAFETY FILTER 2: Check FVG Exists
        # ========================================================================
        if pd.isna(latest.get('fvg_type')) or latest.get('fvg_type') == 'none':
            return {'type': 'NONE', 'reason': 'No FVG detected'}
        
        # ========================================================================
        # SAFETY FILTER 3: STRICT Confluence Score (NO 0.75 DISCOUNT)
        # ========================================================================
        conf_score = latest.get('fvg_confluence_score', 0)
        is_valid_fvg = latest.get('fvg_valid', False) and conf_score >= confluenceThreshold
        
        if not is_valid_fvg:
            return {
                'type': 'NONE',
                'reason': f'Confluence too low ({conf_score:.0f} < {confluenceThreshold})'
            }
        
        # ========================================================================
        # SAFETY FILTER 4: HTF Bias MUST Align with Trade Direction (if enabled)
        # ========================================================================
        htf_bias = latest.get('htf_bias', 0)
        fvg_type = latest.get('fvg_type')
        
        if safety_settings.get('enable_htf_filter', True):
            if fvg_type == 'bullish' and htf_bias < 0:
                return {
                    'type': 'NONE',
                    'reason': 'Bullish FVG but HTF bias is BEARISH - skipped'
                }
            
            if fvg_type == 'bearish' and htf_bias > 0:
                return {
                    'type': 'NONE',
                    'reason': 'Bearish FVG but HTF bias is BULLISH - skipped'
                }
        
        # ========================================================================
        # SAFETY FILTER 5: ADX Trend Strength (if enabled)
        # ========================================================================
        if safety_settings.get('enable_adx_filter', True):
            adx = latest.get('adx', 0)
            if adx < 20:
                return {
                    'type': 'NONE',
                    'reason': f'Weak trend (ADX {adx:.1f} < 20) - avoid ranging market'
                }
        
        # ========================================================================
        # SAFETY FILTER 6: Volume Confirmation (if enabled)
        # ========================================================================
        if safety_settings.get('enable_volume_filter', True):
            volume_ratio = latest.get('volume', 0) / latest.get('volume_ma', 1) if latest.get('volume_ma', 0) > 0 else 0
            if volume_ratio < 0.8:
                return {
                    'type': 'NONE',
                    'reason': f'Low volume ({volume_ratio:.1%} of avg) - wait for confirmation'
                }
        
        # ========================================================================
        # SAFETY FILTER 7: RSI Overbought/Oversold (stricter: 70/30 instead of 80/20)
        # ========================================================================
        rsi = latest.get('rsi', 50)
        atr = latest.get('atr', latest['close'] * 0.01)
        close = latest['close']
        adx = latest.get('adx', 0)
        
        # Get risk-reward ratio from settings
        rr_ratio = safety_settings.get('risk_reward_ratio', 3)
        
        # ---- BULLISH SIGNAL (Bullish FVG + RSI not overbought + HTF bullish) ----
        if fvg_type == 'bullish':
            if rsi > 70:
                return {'type': 'NONE', 'reason': f'RSI overbought ({rsi:.1f}) - wait for pullback'}
            
            has_bos = latest.get('bos_bullish', False)
            has_order_block = latest.get('order_block_bullish', False)
            
            # Entry: Above FVG high
            entry = latest.get('fvg_upper', close) + (atr * 0.1)
            # Stop Loss: Below FVG or Order Block low
            if has_order_block:
                stop_loss = latest.get('ob_low', latest.get('fvg_lower', close)) - (atr * 0.1)
            else:
                stop_loss = latest.get('fvg_lower', close) - (atr * 0.15)
            
            risk = entry - stop_loss
            
            # Use configurable Risk-Reward Ratio
            take_profit = entry + (risk * rr_ratio)
            
            bos_text = " + BOS" if has_bos else ""
            ob_text = " + OB" if has_order_block else ""

            # Check if similar setups recently failed
            block, block_reason = self.trade_memory.should_avoid_similar_setup(
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
        
        # ---- BEARISH SIGNAL (Bearish FVG + RSI not oversold + HTF bearish) ----
        if fvg_type == 'bearish':
            if rsi < 30:
                return {'type': 'NONE', 'reason': f'RSI oversold ({rsi:.1f}) - wait for bounce'}
            
            has_bos = latest.get('bos_bearish', False)
            has_order_block = latest.get('order_block_bearish', False)
            
            # Entry: Below FVG low
            entry = latest.get('fvg_lower', close) - (atr * 0.1)
            # Stop Loss: Above FVG or Order Block high
            if has_order_block:
                stop_loss = latest.get('ob_high', latest.get('fvg_upper', close)) + (atr * 0.1)
            else:
                stop_loss = latest.get('fvg_upper', close) + (atr * 0.15)
            
            risk = stop_loss - entry
            
            # Use configurable Risk-Reward Ratio
            take_profit = entry - (risk * rr_ratio)
            
            bos_text = " + BOS" if has_bos else ""
            ob_text = " + OB" if has_order_block else ""

            # Check if similar setups recently failed
            block, block_reason = self.trade_memory.should_avoid_similar_setup(
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
    
    def execute_trade(self, signal, df, timeframe):
        """Execute a trade if signal is generated"""
        if signal['type'] == 'NONE':
            return None
        
        latest = df.iloc[-1]
        entry_price = signal['entry']
        
        # ========== DEDUPLICATION: Check database for recent trades at this entry zone ==========
        # This survives Streamlit reruns and prevents duplicate entries
        
        # 1. Check in-memory open trades
        tolerance = entry_price * 0.01  # 1% tolerance (stricter than before)
        
        for existing_trade_id, existing_trade in self.open_trades.items():
            # Only check trades in the same direction
            if existing_trade['type'] == signal['type']:
                price_diff = abs(existing_trade['entry'] - entry_price)
                if price_diff <= tolerance:
                    # Entry is too close to an existing open trade - SKIP THIS TRADE
                    return None
        
        # 2. Check database for recent trades in the same timeframe (last 10 trades)
        conn = sqlite3.connect(self.trade_memory.db_path)
        recent_db_trades = conn.execute(
            """
            SELECT entry_price, result FROM trades 
            WHERE timeframe = ? 
            ORDER BY entry_time DESC LIMIT 10
            """,
            (timeframe,)
        ).fetchall()
        conn.close()
        
        # Check if any recent trade (open or recently closed) is within tolerance
        for db_entry_price, result in recent_db_trades:
            if db_entry_price is not None:
                price_diff = abs(db_entry_price - entry_price)
                # If within tolerance and still open (result is None), skip
                if price_diff <= tolerance and result is None:
                    return None
        
        # Position size based on risk
        risk_per_trade = self.balance * 0.02  # Risk 2% per trade
        if signal['risk'] > 0:
            position_size = risk_per_trade / signal['risk']
        else:
            return None
        
        # Create trade
        direction = signal.get('type', 'BUY')
        trade_id = self.trade_memory.log_trade(
            timeframe=timeframe,
            entry_price=signal['entry'],
            stop_loss=signal['stop_loss'],
            take_profit=signal['take_profit'],
            confluence_score=latest.get('fvg_confluence_score', 0),
            rsi=latest.get('rsi', 50),
            htf_bias=latest.get('htf_bias', 0),
            fvg_type=latest.get('fvg_type', 'none'),
            direction=direction,
            entry_reason=signal.get('reason', 'SMC/FVG signal')
        )
        
        self.open_trades[trade_id] = {
            'timeframe': timeframe,
            'type': signal['type'],
            'entry': signal['entry'],
            'stop_loss': signal['stop_loss'],
            'take_profit': signal['take_profit'],
            'position_size': position_size,
            'risk': signal['risk']
        }
        
        return trade_id
    
    def update_open_trades(self, current_price, candle_high=None, candle_low=None):
        """Check if any open trades hit TP/SL using current price and candle range."""
        closed_trades = []
        # Always sync from DB first so Streamlit reruns keep state aligned.
        self.sync_open_trades_from_db()

        hi = float(candle_high) if candle_high is not None else float(current_price)
        lo = float(candle_low) if candle_low is not None else float(current_price)
        
        for trade_id, trade in list(self.open_trades.items()):
            close_price = None
            result = None

            # Range-aware hit detection catches wick touches (not only candle close touches).
            if trade['type'] == 'BUY':
                hit_tp = (float(current_price) >= float(trade['take_profit'])) or (hi >= float(trade['take_profit']))
                hit_sl = (float(current_price) <= float(trade['stop_loss'])) or (lo <= float(trade['stop_loss']))

                if hit_tp and hit_sl:
                    # Conservative tie-breaker when both touched in same candle.
                    close_price = trade['stop_loss']
                    result = 'LOSS'
                elif hit_tp:
                    close_price = trade['take_profit']
                    result = 'WIN'
                elif hit_sl:
                    close_price = trade['stop_loss']
                    result = 'LOSS'
            else:
                hit_tp = (float(current_price) <= float(trade['take_profit'])) or (lo <= float(trade['take_profit']))
                hit_sl = (float(current_price) >= float(trade['stop_loss'])) or (hi >= float(trade['stop_loss']))

                if hit_tp and hit_sl:
                    # Conservative tie-breaker when both touched in same candle.
                    close_price = trade['stop_loss']
                    result = 'LOSS'
                elif hit_tp:
                    close_price = trade['take_profit']
                    result = 'WIN'
                elif hit_sl:
                    close_price = trade['stop_loss']
                    result = 'LOSS'

            if close_price is not None:
                pnl = (close_price - trade['entry']) if trade['type'] == 'BUY' else (trade['entry'] - close_price)
                realized = pnl * trade['position_size']
                self.trade_memory.close_trade(trade_id, close_price)
                self.balance += realized
                closed_trades.append((trade_id, result, realized))
                del self.open_trades[trade_id]
        
        self.equity = self.balance
        return closed_trades

# ============================================================================
# MODULE 4: MACHINE LEARNING MODEL (RANDOM FOREST)
# ============================================================================

class FVGPredictor:
    """Train and predict FVG success probability using Random Forest"""
    
    def __init__(self, db=None):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
        self.scaler = StandardScaler()
        self.is_trained = False
        self.db = db
        self.adaptive_confluence_threshold = 60.0
        self.feature_cols = [
            'fvg_size', 'rsi', 'hour', 'volume', 'ema_trend',
            'trend_slope_10', 'trend_slope_20', 'trend_volatility_20',
            'atr_pct', 'adx', 'htf_bias', 'displacement_pct', 'sweep_high', 'sweep_low',
            'in_premium', 'in_discount', 'fvg_confluence_score',
            'distance_to_resistance_pct', 'distance_to_support_pct', 'direction'
        ]

    def get_adaptive_confluence_threshold(self):
        """Safe accessor for current adaptive threshold used by the UI."""
        return float(getattr(self, 'adaptive_confluence_threshold', 60.0))
        
    def create_training_data(self, df, lookahead=10, profit_threshold=0.5):
        """
        Create training labels by looking forward in time
        If price moves 0.5% in the FVG direction, label as 1 (Win)
        Otherwise label as 0 (Loss)
        """
        df = df.copy()
        df['target'] = 0
        
        fvg_indices = df[df['fvg_bullish'] | df['fvg_bearish']].index
        df['direction'] = np.where(df['fvg_type'] == 'bullish', 1, np.where(df['fvg_type'] == 'bearish', -1, 0))
        
        for idx in fvg_indices:
            if idx + lookahead >= len(df):
                continue
            
            future_high = df.loc[idx:idx+lookahead, 'high'].max()
            future_low = df.loc[idx:idx+lookahead, 'low'].min()
            current_price = df.loc[idx, 'close']
            
            if df.loc[idx, 'fvg_bullish']:
                # For bullish FVG, check if price bounced up
                if (future_high - current_price) / current_price * 100 >= profit_threshold:
                    df.loc[idx, 'target'] = 1
            
            elif df.loc[idx, 'fvg_bearish']:
                # For bearish FVG, check if price bounced down
                if (current_price - future_low) / current_price * 100 >= profit_threshold:
                    df.loc[idx, 'target'] = 1

            if not bool(df.loc[idx, 'fvg_valid']):
                df.loc[idx, 'target'] = 0
        
        return df
    
    def train(self, df, timeframe='1h'):
        """Train Random Forest model on historical FVG data"""
        # Prepare data
        df_train = self.create_training_data(df)
        fvg_mask = (df_train['fvg_bullish'] | df_train['fvg_bearish']) & (df_train['fvg_valid'])
        local_samples = df_train[fvg_mask].copy()

        if self.db is not None and not local_samples.empty:
            self.db.upsert_training_samples(local_samples, timeframe)
            db_samples = self.db.load_training_samples()
        else:
            db_samples = pd.DataFrame()

        if not db_samples.empty:
            X = db_samples[self.feature_cols].fillna(0)
            y = db_samples['target'].astype(int)
        else:
            X = local_samples[self.feature_cols].fillna(0)
            y = local_samples['target'].astype(int)
        
        if len(X) > 10 and len(np.unique(y)) > 1:  # Need minimum samples and both classes
            X_scaled = self.scaler.fit_transform(X)
            self.model.fit(X_scaled, y)
            self.is_trained = True
            accuracy = self.model.score(X_scaled, y)
            return accuracy
        self.is_trained = False
        return 0.0
    
    def predict_fvg_success(self, df):
        """Predict success probability for the most recent FVG"""
        if not self.is_trained:
            return None
        
        # Check if latest candle has FVG
        latest = df.iloc[-1]
        if not (latest['fvg_bullish'] or latest['fvg_bearish']):
            return None

        if not bool(latest.get('fvg_valid', False)):
            return None

        latest_row = df.iloc[[-1]].copy()
        latest_row['direction'] = np.where(latest_row['fvg_type'] == 'bullish', 1, np.where(latest_row['fvg_type'] == 'bearish', -1, 0))
        X = latest_row[self.feature_cols].fillna(0)
        X_scaled = self.scaler.transform(X)
        
        # Get probability of class 1 (Success)
        if 1 not in self.model.classes_:
            return None
        probability = self.model.predict_proba(X_scaled)[0][list(self.model.classes_).index(1)]
        return probability * 100
    
    def learn_from_trades(self, trade_memory):
        """
        Automatically retrain on closed trades - ML learns from wins/losses
        This improves model accuracy over time by using actual trade results
        Adjusts signal parameters, thresholds, and weights based on performance
        """
        if not isinstance(trade_memory, TradeMemory):
            return False
        
        try:
            # Get all closed trades
            closed_trades = trade_memory.get_recent_trades(limit=1000)
            if not closed_trades or len(closed_trades) < 3:
                return False
            
            # Create training data from trade results
            learning_data = []
            for trade in closed_trades:
                trade_id, tf, entry_time, entry_price, sl, tp, exit_time, exit_price, pnl, pnl_pct, result = trade
                
                # Label: 1 if win, 0 if loss
                label = 1 if result == 'WIN' else 0
                
                # Extract the entry signal confluence/RSI info from database
                conn = sqlite3.connect(trade_memory.db_path)
                signal_info = conn.execute(
                    """
                    SELECT confluence_score, rsi_at_entry, htf_bias, fvg_type 
                    FROM trades WHERE trade_id = ?
                    """,
                    (trade_id,)
                ).fetchone()
                conn.close()
                
                if signal_info:
                    confluence, rsi, htf_bias, fvg_type = signal_info
                    learning_data.append({
                        'confluence_score': confluence or 60,
                        'rsi': rsi or 50,
                        'htf_bias': htf_bias or 0,
                        'fvg_type': fvg_type or 'none',
                        'pnl_pct': pnl_pct or 0,
                        'result': result,
                        'target': label
                    })
            
            if not learning_data:
                return False
            
            learn_df = pd.DataFrame(learning_data)
            
            # ===== CALCULATE PERFORMANCE METRICS =====
            total_trades = len(learn_df)
            winning_trades = len(learn_df[learn_df['target'] == 1])
            losing_trades = len(learn_df[learn_df['target'] == 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_win = learn_df[learn_df['target'] == 1]['pnl_pct'].mean() if winning_trades > 0 else 0
            avg_loss = learn_df[learn_df['target'] == 0]['pnl_pct'].mean() if losing_trades > 0 else 0
            
            # Store metrics for UI display
            self.total_trades_analyzed = total_trades
            self.win_rate = win_rate
            self.avg_win_pct = avg_win
            self.avg_loss_pct = avg_loss
            
            wins = learn_df[learn_df['target'] == 1]
            losses = learn_df[learn_df['target'] == 0]
            
            if len(wins) > 0 and len(losses) > 0:
                # ===== ANALYZE WINNING VS LOSING PATTERNS =====
                self.winning_confluence = wins['confluence_score'].mean()
                self.losing_confluence = losses['confluence_score'].mean()
                self.winning_rsi_range = (wins['rsi'].min(), wins['rsi'].max())
                self.losing_rsi_range = (losses['rsi'].min(), losses['rsi'].max())
                
                # FVG Type Performance
                fvg_performance = learn_df.groupby('fvg_type')['target'].agg(['sum', 'count'])
                fvg_performance['win_rate'] = (fvg_performance['sum'] / fvg_performance['count'] * 100)
                self.fvg_performance = fvg_performance.to_dict()
                
                # HTF Bias Performance
                bias_performance = learn_df.groupby('htf_bias')['target'].agg(['sum', 'count'])
                bias_performance['win_rate'] = (bias_performance['sum'] / bias_performance['count'] * 100)
                self.bias_performance = bias_performance.to_dict()
                
                # ===== ADAPTIVE PARAMETER ADJUSTMENT =====
                # Adjust confluence threshold based on trade performance
                if win_rate > 60:
                    self.adaptive_confluence_threshold = min(self.winning_confluence * 0.95, 70)
                elif win_rate > 50:
                    self.adaptive_confluence_threshold = min(self.winning_confluence * 0.85, 65)
                else:
                    self.adaptive_confluence_threshold = max(self.losing_confluence * 1.15, 55)
                
                # Store trade stats for model retraining
                self.recent_trade_performance = {
                    'total': total_trades,
                    'wins': winning_trades,
                    'losses': losing_trades,
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'confluence_threshold': self.adaptive_confluence_threshold
                }
                
                return True
            
            return False
        
        except Exception as e:
            print(f"Error learning from trades: {e}")
            return False


# ============================================================================
# STREAMLIT APP CONFIGURATION
# ============================================================================

st.set_page_config(page_title="ML Trading Dashboard - TradingView Style", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for TradingView-like styling
st.markdown("""
<style>
    body {
        background-color: #f6efe4;
        color: #4f3c2b;
    }
    .main {
        background-color: #f6efe4;
    }
    .stMetric {
        background-color: #fff9f0;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid #b18457;
        border: 1px solid #e6d7c2;
        box-shadow: 0 1px 3px rgba(92, 62, 36, 0.08);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f3e7d7;
        color: #5f4630;
        padding: 10px 18px;
        border: 1px solid #d9c7ad;
        border-radius: 8px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #b18457;
        color: #fff9f0;
    }
    h1, h2, h3 {
        color: #4f3c2b;
        letter-spacing: 0.2px;
    }
    .stDataFrame, .stTable {
        border: 1px solid #e1d2bf;
        border-radius: 10px;
        overflow: hidden;
    }
    .stButton > button {
        background: #b18457;
        color: #fff9f0;
        border: 1px solid #a17246;
        border-radius: 8px;
    }
    .stButton > button:hover {
        background: #9f744d;
        color: #fff9f0;
    }
</style>
""", unsafe_allow_html=True)

try:
    st.title("📊 Professional ML Trading Dashboard")
    st.markdown("**Real-Time Bitcoin Analysis | Smart Money Concepts | Clean Execution Intelligence**")
    
    # ========================================================================
    # TRADING STATUS BANNER (SHOW IF PAUSED DUE TO LOW WIN RATE)
    # ========================================================================
    if 'trade_executor' in st.session_state:
        stats = st.session_state.trade_executor.trade_memory.get_overall_stats()
        if stats['total_trades'] >= 10:
            win_rate = stats['win_rate']
            min_threshold = st.session_state.get('safety_settings', {}).get('min_win_rate_threshold', 35)
            
            if win_rate < min_threshold:
                st.error(f"""
                ### ⛔ TRADING PAUSED - Low Win Rate
                **Current Win Rate:** {win_rate:.1f}% (Threshold: {min_threshold}%)
                
                **Action Required:** Trading has been automatically paused to prevent further losses.
                - Review the ML Learning dashboard below
                - Adjust confluence threshold or safety filters
                - Close losing trades manually if needed
                - Lower the Min Win Rate threshold in sidebar to resume (not recommended)
                """)
            else:
                st.success(f"✅ **Trading Active** | Win Rate: {win_rate:.1f}% ✓ | Total Trades: {stats['total_trades']}")

    # Initialize session state for continuous updates
    if 'last_update' not in st.session_state:
        st.session_state.last_update = datetime.now()

    # Only initialize Streamlit session state when running as a Streamlit app (not headless bot)
    if 'selected_timeframe' not in st.session_state:
        st.session_state.selected_timeframe = '1h'
    if 'trend_db' not in st.session_state:
        st.session_state.trend_db = TrendMLDatabase()
    if 'predictor' not in st.session_state or st.session_state.predictor.db is None or st.session_state.predictor.db.db_path != st.session_state.trend_db.db_path:
        st.session_state.predictor = FVGPredictor(db=st.session_state.trend_db)
    if 'trade_executor' not in st.session_state:
        st.session_state.trade_executor = TradeExecutor(initial_balance=10000)
except Exception:
    # Not running in Streamlit or session state not available (e.g., being imported as module)
    pass

# Suppress browser console warnings for theme properties
st.markdown("""
<script>
const originalWarn = console.warn;
console.warn = function(...args) {
    const msg = args.join(' ');
    if (msg.includes('Cannot redefine property: ethereum') ||
        msg.includes('theme.sidebar') ||
        msg.includes('widgetBackgroundColor') ||
        msg.includes('widgetBorderColor') ||
        msg.includes('skeletonBackgroundColor')) {
        return;
    }
    originalWarn.apply(console, args);
};
</script>
""", unsafe_allow_html=True)

# ============================================================================
# SIDEBAR CONTROLS (TradingView Style)
# ============================================================================

#st.sidebar.title("⚙️ Settings")
timeframes = ['1w', '1d', '4h', '2h', '1h', '15m', '5m', '1m']
selected_timeframe = st.sidebar.radio("Choose Timeframe:", timeframes, index=4, horizontal=False)

# Zone View Mode
st.sidebar.markdown("### 👁️ Support/Resistance View Mode")
view_mode = st.sidebar.radio(
    "Choose View:",
    ["Single Timeframe (Current TF Only)", "All Timeframes (Multi-TF)"],
    index=0,
    horizontal=False,
    help="Single: Shows only zones from selected timeframe | All: Shows all timeframes together"
)
show_all_timeframes = "All Timeframes" in view_mode

# Auto-refresh controls
st.sidebar.markdown("### 🔄 Refresh Settings")
refresh_enabled = st.sidebar.checkbox("Enable Auto-Refresh", value=True)
refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 10, 600, 60)
high_performance_mode = st.sidebar.checkbox(
    "⚡ High Performance Mode",
    value=True,
    help="Faster UI by throttling expensive model updates/scans and reducing heavy chart interactivity."
)
turbo_mode = st.sidebar.checkbox(
    "🚀 Turbo Mode (Max Speed)",
    value=True,
    help="Scans only fast execution timeframes per refresh, caches recommendations longer, and hides heavy debug table."
)
scan_cache_seconds = st.sidebar.slider("Scan Cache (seconds)", 20, 300, 90)

# SMC Settings
st.sidebar.markdown("### 🎯 SMC Settings")
show_fvg = st.sidebar.checkbox("Show Fair Value Gaps", value=True)
show_bos = st.sidebar.checkbox("Show Break of Structure", value=True)
show_swing = st.sidebar.checkbox("Show Swing Points", value=True)

# Model Settings
st.sidebar.markdown("### 🤖 ML Model")
prob_threshold = st.sidebar.slider("Probability Threshold (%)", 30, 95, 65)
min_confluence_threshold = st.sidebar.slider("Min Confluence Score", 40, 90, 60)

# ========================================================================
# SAFETY CONTROLS (NEW)
# ========================================================================
st.sidebar.markdown("### 🛡️ Safety Controls")
st.sidebar.info("**Filters to reduce losing trades:**")

enable_htf_filter = st.sidebar.checkbox(
    "✅ HTF Bias Filter",
    value=True,
    help="Only trade when HTF bias aligns with signal direction"
)

enable_adx_filter = st.sidebar.checkbox(
    "✅ ADX Trend Filter",
    value=True,
    help="Require ADX > 20 to avoid ranging markets"
)

enable_volume_filter = st.sidebar.checkbox(
    "✅ Volume Filter",
    value=True,
    help="Require above-average volume for confirmation"
)

min_win_rate_threshold = st.sidebar.slider(
    "Min Win Rate to Continue (%)",
    20, 50, 35,
    help="Pause trading if win rate drops below this threshold (needs 10+ trades)"
)

risk_reward_ratio = st.sidebar.selectbox(
    "Risk:Reward Ratio",
    options=[2, 3, 4, 5],
    index=1,
    help="Higher = More profit per win, but trades may take longer to hit TP"
)

# Store safety settings in session state for access in signal generation
if 'safety_settings' not in st.session_state:
    st.session_state.safety_settings = {}

st.session_state.safety_settings = {
    'enable_htf_filter': enable_htf_filter,
    'enable_adx_filter': enable_adx_filter,
    'enable_volume_filter': enable_volume_filter,
    'min_win_rate_threshold': min_win_rate_threshold,
    'risk_reward_ratio': risk_reward_ratio
}

# ========================================================================
# CLEAR ALL TRADES (RESET DATABASE)
# ========================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🗑️ Reset Database")
st.sidebar.warning("⚠️ **Danger Zone**")

# Initialize confirmation state
if 'confirm_clear' not in st.session_state:
    st.session_state['confirm_clear'] = False

if not st.session_state.get('confirm_clear', False):
    if st.sidebar.button("🗑️ Clear All Trades", type="secondary"):
        st.session_state['confirm_clear'] = True
        st.rerun()
else:
    st.sidebar.error("⚠️ Are you sure? This cannot be undone!")
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("✅ Yes, Clear", type="primary"):
            try:
                if st.session_state.trade_executor.trade_memory.clear_all_trades():
                    # Clear open trades from memory
                    st.session_state.trade_executor.open_trades = {}
                    # Reset balance
                    st.session_state.trade_executor.balance = 10000
                    st.session_state.trade_executor.equity = 10000
                    st.session_state['confirm_clear'] = False
                    st.sidebar.success("✅ All trades cleared! Starting fresh.")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Failed to clear trades")
                    st.session_state['confirm_clear'] = False
            except Exception as e:
                st.sidebar.error(f"❌ Error: {str(e)}")
                st.session_state['confirm_clear'] = False
    
    with col2:
        if st.button("❌ Cancel"):
            st.session_state['confirm_clear'] = False
            st.rerun()

st.sidebar.info("""
**This will:**
- Delete all open trades
- Delete all closed trades
- Clear trade statistics
- Clear ML training data
- Reset balance to $10,000

Use this to test accuracy from scratch.
""")

# Background Trading Info
st.sidebar.markdown("### 🚀 Background Trading")
st.sidebar.warning("""
**How It Works:**
✅ Streamlit server runs INDEPENDENTLY
✅ Trades execute even if you close the browser
✅ Data auto-refreshes per interval
✅ Just keep terminal/process running

**To Stop Trading:**
❌ Close the browser = Still trading
❌ Close the terminal = Trades stop
""")

st.sidebar.markdown("---")
st.sidebar.markdown("**Last Updated:** " + datetime.now().strftime("%H:%M:%S"))

# ============================================================================
# DATA FETCHING AND PROCESSING
# ============================================================================

fetcher = BinanceDataFetcher()


def compute_htf_bias(df_htf):
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

# Determine candles to fetch based on timeframe
candle_limit = {
    '1w': 500,
    '1d': 500,
    '4h': 500,
    '2h': 500,
    '1h': 500,
    '15m': 1000,
    '5m': 1200,
    '1m': 1200
}

df = fetcher.fetch_historical_data(timeframe=selected_timeframe, limit=candle_limit.get(selected_timeframe, 500))

if df is not None:
    # Fetch all timeframe data for HTF bias
    df_1w = fetcher.fetch_historical_data(timeframe='1w', limit=500)
    df_1d = fetcher.fetch_historical_data(timeframe='1d', limit=500)
    df_4h = fetcher.fetch_historical_data(timeframe='4h', limit=500)
    df_2h = fetcher.fetch_historical_data(timeframe='2h', limit=500)
    df_1h = fetcher.fetch_historical_data(timeframe='1h', limit=500)
    
    bias_1w = compute_htf_bias(df_1w)
    bias_1d = compute_htf_bias(df_1d)
    bias_4h = compute_htf_bias(df_4h)
    bias_2h = compute_htf_bias(df_2h)
    bias_1h = compute_htf_bias(df_1h)
    
    # Determine combined bias (higher timeframe takes precedence)
    if bias_1w != 0:
        combined_bias = bias_1w
    elif bias_1d != 0:
        combined_bias = bias_1d
    elif bias_4h != 0:
        combined_bias = bias_4h
    elif bias_2h != 0:
        combined_bias = bias_2h
    else:
        combined_bias = bias_1h

    st.sidebar.markdown("### 🧭 HTF Bias (All Timeframes)")
    st.sidebar.write(f"📈 1W: {'🟢 Bullish' if bias_1w == 1 else '🔴 Bearish' if bias_1w == -1 else '⚪ Neutral'}")
    st.sidebar.write(f"📅 1D: {'🟢 Bullish' if bias_1d == 1 else '🔴 Bearish' if bias_1d == -1 else '⚪ Neutral'}")
    st.sidebar.write(f"🕐 4H: {'🟢 Bullish' if bias_4h == 1 else '🔴 Bearish' if bias_4h == -1 else '⚪ Neutral'}")
    st.sidebar.write(f"⏰ 2H: {'🟢 Bullish' if bias_2h == 1 else '🔴 Bearish' if bias_2h == -1 else '⚪ Neutral'}")
    st.sidebar.write(f"🕰️ 1H: {'🟢 Bullish' if bias_1h == 1 else '🔴 Bearish' if bias_1h == -1 else '⚪ Neutral'}")
    st.sidebar.markdown(f"**🎯 Combined: {'🟢 Bullish' if combined_bias == 1 else '🔴 Bearish' if combined_bias == -1 else '⚪ Neutral'}**")

    # Apply SMC features
    df = SMCIndicators.engineer_all_features(
        df,
        htf_bias=combined_bias,
        min_confluence_threshold=min_confluence_threshold
    )
    
    # Train model with throttling to reduce lag on reruns.
    if 'last_model_train_ts' not in st.session_state:
        st.session_state.last_model_train_ts = datetime.min
    if 'last_model_train_candle' not in st.session_state:
        st.session_state.last_model_train_candle = None
    if 'last_model_accuracy' not in st.session_state:
        st.session_state.last_model_accuracy = 0.0

    latest_candle_key = str(df.iloc[-1]['timestamp'])
    elapsed_train = (datetime.now() - st.session_state.last_model_train_ts).total_seconds()
    train_interval = 180 if high_performance_mode else 45
    should_train = (
        st.session_state.last_model_train_candle != latest_candle_key
        and elapsed_train >= train_interval
    )

    if should_train:
        with st.spinner("🤖 Updating ML model with trend database..."):
            accuracy = st.session_state.predictor.train(df, timeframe=selected_timeframe)
        st.session_state.last_model_accuracy = accuracy
        st.session_state.last_model_train_ts = datetime.now()
        st.session_state.last_model_train_candle = latest_candle_key
        st.sidebar.success(f"✅ Model updated! Accuracy: {accuracy:.2%}")
    else:
        st.sidebar.info(f"⚡ Using cached model | Accuracy: {st.session_state.last_model_accuracy:.2%}")
    
    # Get prediction for latest FVG
    latest_prob = st.session_state.predictor.predict_fvg_success(df)
    st.session_state.trend_db.log_trend_snapshot(df.iloc[-1], selected_timeframe, latest_prob)
    
    # ========================================================================
    # TRADING SYSTEM (SIGNAL GENERATION & EXECUTION)
    # ========================================================================
    
    # Display signal diagnostics
    latest = df.iloc[-1]
    with st.sidebar.expander("🔍 **Signal Diagnostics**", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("FVG Type", latest.get('fvg_type', 'none').upper())
            st.metric("FVG Valid", "✅ Yes" if latest.get('fvg_valid', False) else "❌ No")
            st.metric("Confluence Score", f"{latest.get('fvg_confluence_score', 0):.1f} / {min_confluence_threshold}")
            st.metric("RSI", f"{latest.get('rsi', 50):.1f}")
        
        with col2:
            st.metric("BOS Bullish", "🟢 Yes" if latest.get('bos_bullish', False) else "🔴 No")
            st.metric("BOS Bearish", "🔴 Yes" if latest.get('bos_bearish', False) else "🟢 No")
            st.metric("ATR %", f"{latest.get('atr_pct', 0):.3f}%")
            st.metric("ADX", f"{latest.get('adx', 0):.1f}")
        
        # Show why no signal if none
        if latest.get('fvg_type', 'none') == 'none':
            st.warning("⚠️ No FVG formed yet")
        elif not latest.get('fvg_valid', False):
            st.warning(f"⚠️ FVG not valid: {latest.get('fvg_invalid_reason', 'Unknown')}")
        elif latest.get('fvg_confluence_score', 0) < min_confluence_threshold:
            st.warning(f"⚠️ Confluence score too low ({latest.get('fvg_confluence_score', 0):.0f} < {min_confluence_threshold})")
        elif latest.get('fvg_type', 'none') == 'bullish' and not latest.get('bos_bullish', False):
            st.warning("⚠️ Waiting for Bullish BOS")
        elif latest.get('fvg_type', 'none') == 'bearish' and not latest.get('bos_bearish', False):
            st.warning("⚠️ Waiting for Bearish BOS")
    
    # ========================================================================
    # MULTI-TIMEFRAME TRADING (Generate Signals on All Timeframes)
    # ========================================================================
    
    # Initialize signal cooldown tracker in session state to prevent duplicate trades on reruns
    if 'signal_cooldown' not in st.session_state:
        st.session_state.signal_cooldown = {}  # {signal_key: candle_index}
    if 'trades_opened_this_session' not in st.session_state:
        st.session_state.trades_opened_this_session = {}  # {timeframe: count}
    
    all_timeframes = ['1w', '1d', '4h', '2h', '1h', '15m', '5m', '1m']
    scan_timeframes = ['1h', '15m', '5m', '1m'] if turbo_mode else all_timeframes
    multitf_signals = {}
    multitf_debug = []
    multitf_data = {}
    
    st.sidebar.markdown("### 📡 Multi-Timeframe Scan Status")
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    
    use_cached_scan = False
    effective_scan_cache_seconds = max(scan_cache_seconds, 120) if turbo_mode else scan_cache_seconds
    if high_performance_mode and 'last_multitf_scan' in st.session_state:
        scan_elapsed = (datetime.now() - st.session_state.last_multitf_scan).total_seconds()
        cached_scan_timeframes = st.session_state.get('scan_timeframes_cache', all_timeframes)
        if scan_elapsed < effective_scan_cache_seconds and 'multitf_signals_cache' in st.session_state and cached_scan_timeframes == scan_timeframes:
            use_cached_scan = True
            multitf_signals = st.session_state.multitf_signals_cache
            multitf_debug = st.session_state.multitf_debug_cache
            multitf_data = st.session_state.get('multitf_data_cache', {})

    if not use_cached_scan:
        for idx, tf in enumerate(scan_timeframes):
            try:
                status_text.text(f"🔍 Scanning {tf}...")
                progress_bar.progress((idx + 1) / len(scan_timeframes))

                # Fetch and process data for this timeframe
                df_tf = fetcher.fetch_historical_data(timeframe=tf, limit=candle_limit.get(tf, 500))

                if df_tf is None or len(df_tf) < 5:
                    multitf_debug.append(f"⚠️ {tf}: Insufficient data ({len(df_tf) if df_tf is not None else 0} candles)")
                    continue

                # Apply SMC features with adjusted confluence for timeframe
                # Higher TFs = more reliable = LOWER confluence needed
                # Lower TFs = noisier = HIGHER confluence needed
                tf_confluence = {
                    '1w': max(20, min_confluence_threshold - 25),
                    '1d': max(25, min_confluence_threshold - 20),
                    '4h': max(30, min_confluence_threshold - 15),
                    '2h': min_confluence_threshold - 10,
                    '1h': min_confluence_threshold,
                    '15m': min_confluence_threshold + 5,
                    '5m': min_confluence_threshold + 15,
                    '1m': min_confluence_threshold + 20
                }

                adj_confluence = tf_confluence.get(tf, min_confluence_threshold)

                df_tf = SMCIndicators.engineer_all_features(
                    df_tf,
                    htf_bias=combined_bias,
                    min_confluence_threshold=adj_confluence
                )
                multitf_data[tf] = df_tf

                latest_tf = df_tf.iloc[-1]
                fvg_type = latest_tf.get('fvg_type', 'none')
                conf_score = latest_tf.get('fvg_confluence_score', 0)
                fvg_valid = latest_tf.get('fvg_valid', False)
                bos_bull = latest_tf.get('bos_bullish', False)
                bos_bear = latest_tf.get('bos_bearish', False)
                ob_bull = latest_tf.get('order_block_bullish', False)
                ob_bear = latest_tf.get('order_block_bearish', False)
                current_candle_idx = len(df_tf) - 1

                debug_details = f"FVG={fvg_type}|Valid={fvg_valid}|Score={conf_score:.0f}/{adj_confluence}|BOS_B={bos_bull}|BOS_S={bos_bear}|OB_B={ob_bull}|OB_S={ob_bear}"
                multitf_debug.append(f"✅ {tf}: {debug_details}")

                # Generate signal for this timeframe
                signal_tf = st.session_state.trade_executor.generate_signal(
                    df_tf,
                    tf,
                    confluenceThreshold=adj_confluence
                )

                # Log signal result (before trying to execute)
                if signal_tf['type'] == 'NONE':
                    multitf_debug[-1] += f" → NONE (Reason: {signal_tf.get('reason', signal_tf.get('blocked_reason', 'No reason'))})"
                else:
                    multitf_debug[-1] += f" → {signal_tf['type']} Signal Generated!"

                if signal_tf['type'] != 'NONE':
                    rounded_entry = round(signal_tf['entry'] * 2) / 2
                    signal_key = f"{tf}_{signal_tf['type']}_{rounded_entry:.2f}"
                    last_candle_executed = st.session_state.signal_cooldown.get(signal_key, -999)
                    candles_since_last = current_candle_idx - last_candle_executed

                    trades_on_tf = st.session_state.trades_opened_this_session.get(tf, 0)

                    if trades_on_tf >= 1:
                        multitf_debug[-1] = f"⏳ {tf}: LIMIT REACHED - Already opened 1 trade (max per session)"
                    elif candles_since_last < 10:
                        multitf_debug[-1] = f"⏳ {tf}: COOLDOWN ({candles_since_last} candles) - {signal_tf['type']} skipped"
                    else:
                        trade_id = st.session_state.trade_executor.execute_trade(signal_tf, df_tf, tf)
                        if trade_id:
                            st.session_state.signal_cooldown[signal_key] = current_candle_idx
                            st.session_state.trades_opened_this_session[tf] = trades_on_tf + 1
                            multitf_signals[tf] = {
                                'trade_id': trade_id,
                                'signal': signal_tf,
                                'data': df_tf,
                                'confluence': adj_confluence
                            }
                            multitf_debug[-1] = f"🟢 {tf}: TRADE #{trade_id} EXECUTED! {signal_tf['type']} @ ${signal_tf['entry']:,.2f}"
                        else:
                            multitf_debug[-1] = f"⚠️ {tf}: Signal generated but TRADE SKIPPED (likely duplicate/open position exists)"
            except Exception as e:
                multitf_debug.append(f"❌ {tf}: Error - {str(e)}")
                continue

        st.session_state.last_multitf_scan = datetime.now()
        st.session_state.multitf_signals_cache = multitf_signals
        st.session_state.multitf_debug_cache = multitf_debug
        st.session_state.multitf_data_cache = multitf_data
        st.session_state.scan_timeframes_cache = scan_timeframes
    else:
        progress_bar.progress(1.0)
        status_text.text("⚡ Using cached multi-timeframe scan")
    
    progress_bar.empty()
    status_text.empty()
    
    # Show scan results with enhanced detail
    if multitf_debug:
        with st.sidebar.expander("📊 Extended Scan Details", expanded=False):
            for debug_msg in multitf_debug:
                if "🟢" in debug_msg or "🟢" in debug_msg:
                    st.sidebar.success(debug_msg)
                elif "❌" in debug_msg:
                    st.sidebar.error(debug_msg)
                elif "⚠️" in debug_msg or "⏳" in debug_msg:
                    st.sidebar.warning(debug_msg)
                else:
                    st.sidebar.info(debug_msg)
    
    if not turbo_mode:
        # Create detailed debug table (expensive rendering, disabled in turbo mode)
        st.markdown("---")
        st.subheader("🔬 **Multi-Timeframe Signal Debug Table**")
        
        debug_table_data = []
        for debug_msg in multitf_debug:
            parts = debug_msg.split(":")
            if len(parts) >= 2:
                tf_name = parts[0].strip().replace("✅", "").replace("🟢", "").replace("⚠️", "").replace("❌", "").strip()
                details = ":".join(parts[1:])
                debug_table_data.append({
                    'Timeframe': tf_name.upper(),
                    'Status': '✅ Trade' if '🟢' in debug_msg and 'TRADE' in debug_msg else ('⚠️ Signal Failed' if '⚠️' in debug_msg else ('❌ Error' if '❌' in debug_msg else '⏳ No Signal')),
                    'Details': details.strip()
                })
        
        if debug_table_data:
            debug_df = pd.DataFrame(debug_table_data)
            st.dataframe(debug_df, use_container_width=True, hide_index=True)
        else:
            st.info("No scan data available")
    else:
        st.info(f"⚡ Turbo Mode active: scanned {len(scan_timeframes)} timeframes ({', '.join(scan_timeframes)})")
    
    
    # Display Multi-Timeframe Trading Status
    st.sidebar.markdown("### 🚀 **Multi-Timeframe Trading Status**")
    
    if multitf_signals:
        st.sidebar.success(f"✅ {len(multitf_signals)} Trades Executed across Timeframes!")
        
        for tf, trade_info in multitf_signals.items():
            signal = trade_info['signal']
            trade_id = trade_info['trade_id']
            conf_threshold = trade_info['confluence']
            
            st.sidebar.success(
                f"**🟢 {tf.upper()} - Trade #{trade_id}**\n"
                f"Direction: {signal['type']}\n"
                f"Entry: ${signal['entry']:,.2f}\n"
                f"SL: ${signal['stop_loss']:,.2f} | TP: ${signal['take_profit']:,.2f}\n"
                f"Reason: {signal.get('reason', 'SMC signal')}\n"
                f"Confluence ({signal.get('reason', '')[:20]}): {signal.get('reason', '')}"
            )
    else:
        st.sidebar.warning(f"⏳ No signals on any timeframe yet (scanned {len(scan_timeframes)} TFs)")
    
    # ========================================================================
    # MULTI-TIMEFRAME STATUS DASHBOARD
    # ========================================================================
    
    st.markdown("---")
    st.subheader("🌍 **Multi-Timeframe Scanning Results**")
    
    # Display each timeframe's status
    col1, col2, col3, col4 = st.columns(4)
    columns = [col1, col2, col3, col4]
    
    tf_status_data = {
        '1W': {'color': '🟣', 'index': 0},
        '1D': {'color': '🟦', 'index': 1},
        '4H': {'color': '🟩', 'index': 2},
        '2H': {'color': '🟨', 'index': 3},
        '1H': {'color': '🟧', 'index': 4},
        '15M': {'color': '🟥', 'index': 5},
        '5M': {'color': '⬛', 'index': 6},
        '1M': {'color': '⬜', 'index': 7},
    }
    
    for tf_upper, tf_lower in [('1W', '1w'), ('1D', '1d'), ('4H', '4h'), ('2H', '2h'), ('1H', '1h'), ('15M', '15m'), ('5M', '5m'), ('1M', '1m')]:
        col_idx = tf_status_data[tf_upper]['index']
        col = columns[col_idx % 4]
        
        # Check if this timeframe was scanned (important for turbo mode)
        if tf_lower not in scan_timeframes:
            col.warning(f"⚡ **{tf_upper}**\nSkipped (Turbo)")
            continue
        
        if tf_lower in multitf_signals:
            # Trade executed
            trade_info = multitf_signals[tf_lower]
            signal_type = trade_info['signal']['type']
            trade_id = trade_info['trade_id']
            col.success(f"""
            ✅ **{tf_upper}**
            Trade #{trade_id}
            {signal_type} Signal Active
            """)
        else:
            # Check debug info
            debug_msg = next((d for d in multitf_debug if tf_upper in d or tf_lower in d), "")
            if "Insufficient data" in debug_msg:
                col.warning(f"⚠️ **{tf_upper}**\nInsufficient data")
            elif "Error" in debug_msg:
                col.error(f"❌ **{tf_upper}**\nFetch error")
            else:
                # Extract details from debug message
                if "Score=" in debug_msg:
                    parts = debug_msg.split("Score=")[1].split("/")
                    score = parts[0]
                    threshold = parts[1] if len(parts) > 1 else "?"
                    col.info(f"""
                    ⏳ **{tf_upper}**
                    Score: {score}/{threshold}
                    Waiting...
                    """)
                else:
                    col.info(f"⏳ **{tf_upper}**\nScanning...")
    
    st.markdown("---")
    
    # Current timeframe analysis
    st.subheader(f"📊 **{selected_timeframe.upper()} Timeframe Analysis**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Price", f"${latest['close']:,.2f}")
        st.metric("FVG Type", latest.get('fvg_type', 'none').upper())
        st.metric("Confluence Score", f"{latest.get('fvg_confluence_score', 0):.0f}/{min_confluence_threshold}")
    
    with col2:
        st.metric("BOS Bullish", "🟢 Yes" if latest.get('bos_bullish', False) else "🔴 No")
        st.metric("BOS Bearish", "🔴 Yes" if latest.get('bos_bearish', False) else "🟢 No")
        st.metric("RSI", f"{latest.get('rsi', 50):.1f}")
    
    with col3:
        st.metric("Order Block (B)", "✅" if latest.get('order_block_bullish', False) else "❌")
        st.metric("Order Block (S)", "✅" if latest.get('order_block_bearish', False) else "❌")
        st.metric("HTF Bias", f"{'🟢 Bullish' if combined_bias == 1 else '🔴 Bearish' if combined_bias == -1 else '⚪ Neutral'}")
    
    # Manual trade trigger for testing
    with st.sidebar.expander("🎮 **Manual Trade Control**"):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🟢 Test BUY", key="test_buy"):
                test_signal = {
                    'type': 'BUY',
                    'entry': latest['close'] * 1.005,
                    'stop_loss': latest['close'] * 0.99,
                    'take_profit': latest['close'] * 1.02,
                    'risk': latest['close'] * 0.01,
                    'reason': 'MANUAL TEST'
                }
                test_trade = st.session_state.trade_executor.execute_trade(test_signal, df, selected_timeframe)
                if test_trade:
                    st.success(f"✅ Test BUY Trade Executed! Trade ID: {test_trade}")
        
        with col2:
            if st.button("🔴 Test SELL", key="test_sell"):
                test_signal = {
                    'type': 'SELL',
                    'entry': latest['close'] * 0.995,
                    'stop_loss': latest['close'] * 1.01,
                    'take_profit': latest['close'] * 0.98,
                    'risk': latest['close'] * 0.01,
                    'reason': 'MANUAL TEST'
                }
                test_trade = st.session_state.trade_executor.execute_trade(test_signal, df, selected_timeframe)
                if test_trade:
                    st.success(f"✅ Test SELL Trade Executed! Trade ID: {test_trade}")
    
    # Update open trades based on current price
    current_price = df.iloc[-1]['close']
    current_high = df.iloc[-1]['high']
    current_low = df.iloc[-1]['low']
    closed = st.session_state.trade_executor.update_open_trades(current_price, candle_high=current_high, candle_low=current_low)
    
    # AUTOMATIC LEARNING FROM CLOSED TRADES
    if closed:
        for trade_id, result, pnl in closed:
            if result == 'WIN':
                st.sidebar.success(f"✅ Trade #{trade_id} **WON**! P&L: ${pnl:,.2f}")
            else:
                st.sidebar.error(f"❌ Trade #{trade_id} **LOST**! P&L: ${pnl:,.2f}")
        
        # ML learns from the closed trades - improve predictions automatically
        with st.spinner("🧠 ML Learning from trade results..."):
            learned = st.session_state.predictor.learn_from_trades(st.session_state.trade_executor.trade_memory)
            if learned:
                st.sidebar.info("✨ ML Model Updated! Learned from trade patterns.")
    
    # ========================================================================
    # ML LEARNING PERFORMANCE DASHBOARD
    # ========================================================================
    
    with st.expander("📊 **ML Learning Performance Dashboard**", expanded=False):
        if hasattr(st.session_state.predictor, 'recent_trade_performance'):
            perf = st.session_state.predictor.recent_trade_performance
            
            # Main metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric(
                    "📈 Total Trades Analyzed",
                    f"{perf['total']}",
                    delta=f"{perf['wins']} wins, {perf['losses']} losses"
                )
            
            with col2:
                win_rate_color = "green" if perf['win_rate'] > 55 else "red" if perf['win_rate'] < 45 else "gray"
                st.metric(
                    "🎯 Win Rate",
                    f"{perf['win_rate']:.1f}%",
                    delta=f"{'+' if perf['win_rate'] > 50 else '-'} {abs(perf['win_rate'] - 50):.1f}pp"
                )
            
            with col3:
                st.metric(
                    "📊 Avg Win",
                    f"{perf['avg_win']:.2f}%",
                    delta="Per winning trade"
                )
            
            with col4:
                st.metric(
                    "📉 Avg Loss",
                    f"{perf['avg_loss']:.2f}%",
                    delta="Per losing trade"
                )
            
            with col5:
                adaptive_threshold = st.session_state.predictor.adaptive_confluence_threshold
                st.metric(
                    "🔧 Adaptive Threshold",
                    f"{adaptive_threshold:.0f}",
                    delta="Auto-adjusted from performance"
                )
            
            # ===== FVG TYPE PERFORMANCE =====
            st.subheader("🔍 FVG Type Performance Analysis")
            if hasattr(st.session_state.predictor, 'fvg_performance'):
                fvg_perf = st.session_state.predictor.fvg_performance
                fvg_col1, fvg_col2 = st.columns(2)
                
                with fvg_col1:
                    if 'bullish' in fvg_perf['sum']:
                        bullish_count = fvg_perf['count'].get('bullish', 0)
                        bullish_wins = fvg_perf['sum'].get('bullish', 0)
                        bullish_wr = fvg_perf['win_rate'].get('bullish', 0) if bullish_count > 0 else 0
                        st.info(f"""
                        **Bullish FVGs:**
                        - Trades: {bullish_count}
                        - Wins: {bullish_wins}
                        - Win Rate: {bullish_wr:.1f}%
                        """)
                
                with fvg_col2:
                    if 'bearish' in fvg_perf['sum']:
                        bearish_count = fvg_perf['count'].get('bearish', 0)
                        bearish_wins = fvg_perf['sum'].get('bearish', 0)
                        bearish_wr = fvg_perf['win_rate'].get('bearish', 0) if bearish_count > 0 else 0
                        st.warning(f"""
                        **Bearish FVGs:**
                        - Trades: {bearish_count}
                        - Wins: {bearish_wins}
                        - Win Rate: {bearish_wr:.1f}%
                        """)
            
            # ===== HTF BIAS PERFORMANCE =====
            st.subheader("🧭 HTF Bias Performance Analysis")
            if hasattr(st.session_state.predictor, 'bias_performance'):
                bias_perf = st.session_state.predictor.bias_performance
                bias_col1, bias_col2, bias_col3 = st.columns(3)
                
                with bias_col1:
                    if 1 in bias_perf['sum']:
                        bullish_count = bias_perf['count'].get(1, 0)
                        bullish_wins = bias_perf['sum'].get(1, 0)
                        bullish_wr = bias_perf['win_rate'].get(1, 0) if bullish_count > 0 else 0
                        st.success(f"""
                        **Bullish Bias (+1):**
                        - Trades: {bullish_count}
                        - Wins: {bullish_wins}
                        - Win Rate: {bullish_wr:.1f}%
                        """)
                
                with bias_col2:
                    if 0 in bias_perf['sum']:
                        neutral_count = bias_perf['count'].get(0, 0)
                        neutral_wins = bias_perf['sum'].get(0, 0)
                        neutral_wr = bias_perf['win_rate'].get(0, 0) if neutral_count > 0 else 0
                        st.info(f"""
                        **Neutral Bias (0):**
                        - Trades: {neutral_count}
                        - Wins: {neutral_wins}
                        - Win Rate: {neutral_wr:.1f}%
                        """)
                
                with bias_col3:
                    if -1 in bias_perf['sum']:
                        bearish_count = bias_perf['count'].get(-1, 0)
                        bearish_wins = bias_perf['sum'].get(-1, 0)
                        bearish_wr = bias_perf['win_rate'].get(-1, 0) if bearish_count > 0 else 0
                        st.error(f"""
                        **Bearish Bias (-1):**
                        - Trades: {bearish_count}
                        - Wins: {bearish_wins}
                        - Win Rate: {bearish_wr:.1f}%
                        """)
            
            # ===== LEARNING INSIGHTS =====
            st.subheader("💡 Learning Insights")
            
            if hasattr(st.session_state.predictor, 'winning_confluence'):
                avg_col1, avg_col2, avg_col3 = st.columns(3)
                
                with avg_col1:
                    st.metric("🟢 Winning Avg Confluence", f"{st.session_state.predictor.winning_confluence:.1f}")
                
                with avg_col2:
                    st.metric("🔴 Losing Avg Confluence", f"{st.session_state.predictor.losing_confluence:.1f}")
                
                with avg_col3:
                    confluence_diff = st.session_state.predictor.winning_confluence - st.session_state.predictor.losing_confluence
                    st.metric("📊 Confluence Difference", f"{confluence_diff:.1f}", delta="Winners vs Losers")
            
            # State improvement
            st.success(f"""
            ✨ **Model Improvement Status:**
            - ✅ Analyzing {perf['total']} trades
            - ✅ Confluence threshold automatically adjusted to {adaptive_threshold:.0f}
            - ✅ FVG type performance tracked
            - ✅ HTF bias effectiveness measured
            - ✅ Model accuracy improving with each trade
            """)
        else:
            st.info("⏳ Waiting for closed trades to learn from...")
    
    # ========================================================================
    # ACTIVE TRADES DASHBOARD (All Timeframes)
    # ========================================================================
    
    with st.expander("📋 **Active Trades Across All Timeframes**", expanded=False):
        open_trades = st.session_state.trade_executor.trade_memory.get_open_trades()
        
        if open_trades:
            st.success(f"🟢 **{len(open_trades)} Open Trades**")
            
            # Trade selector for chart highlighting
            trade_options = {f"Trade #{trade[0]} ({trade[1]} - {trade[11]})": {
                'trade_id': trade[0],
                'timeframe': trade[1],
                'entry_time': trade[2],
                'entry_price': trade[3],
                'sl': trade[4],
                'tp': trade[5],
                'direction': trade[11] if trade[11] in ('BUY', 'SELL') else ('BUY' if trade[5] > trade[3] else 'SELL'),
                'entry_reason': trade[12] or 'SMC Signal'
            } for trade in open_trades}
            
            trade_options_list = ["None - Clear Highlights"] + list(trade_options.keys())
            selected_trade_label = st.selectbox(
                "📍 **Select Trade to Highlight on Chart:**",
                trade_options_list,
                key="selected_trade_highlight"
            )
            
            if selected_trade_label != "None - Clear Highlights":
                st.session_state.highlighted_trade = trade_options[selected_trade_label]
                selected_tf = trade_options[selected_trade_label]['timeframe']
                if selected_tf != selected_timeframe:
                    st.warning(f"⚠️ This trade is on **{selected_tf}** timeframe, but you're viewing **{selected_timeframe}**. Switch to {selected_tf} in the sidebar for accurate entry candle visualization.")
                else:
                    st.info(f"📌 **Chart will show:** Entry candle marker, Entry/TP/SL price lines, and vertical line at entry time. Scroll down to see the chart!")
            else:
                st.session_state.highlighted_trade = None
            
            # Create DataFrame for better visualization
            trades_data = []
            total_exposure = 0
            total_potential_profit = 0
            total_potential_loss = 0
            
            for trade_id, tf, entry_time, entry_price, sl, tp, risk, reward, conf_score, rsi_at_entry, fvg_type, direction_db, entry_reason in open_trades:
                current_price_trade = df.iloc[-1]['close']

                direction_db = direction_db if direction_db in ('BUY', 'SELL') else ('BUY' if tp > entry_price else 'SELL')
                if direction_db == 'BUY':
                    direction = 'LONG'
                    unrealized_pnl = current_price_trade - entry_price
                    unrealized_pnl_pct = (unrealized_pnl / entry_price) * 100 if entry_price > 0 else 0
                    distance_to_tp = tp - current_price_trade
                    distance_to_sl = current_price_trade - sl
                else:
                    direction = 'SHORT'
                    unrealized_pnl = entry_price - current_price_trade
                    unrealized_pnl_pct = (unrealized_pnl / entry_price) * 100 if entry_price > 0 else 0
                    distance_to_tp = current_price_trade - tp
                    distance_to_sl = sl - current_price_trade
                
                trades_data.append({
                    'Trade ID': trade_id,
                    'TF': tf,
                    'Type': direction,
                    'Entry': f"${entry_price:,.2f}",
                    'Current': f"${current_price_trade:,.2f}",
                    'P&L': f"${unrealized_pnl:,.2f} ({unrealized_pnl_pct:+.2f}%)",
                    'TP': f"${tp:,.2f}",
                    'SL': f"${sl:,.2f}",
                    'Risk (pips)': f"{distance_to_sl:,.2f}",
                    'Profit (pips)': f"{distance_to_tp:,.2f}",
                    'Entry Time': entry_time.split('T')[1][:5] if 'T' in str(entry_time) else entry_time,
                    'Confluence': f"{conf_score:.0f}",
                    'RSI': f"{rsi_at_entry:.1f}",
                    'Entry Thesis': (entry_reason or 'SMC/FVG signal')[:80],
                })
                
                total_exposure += entry_price
                total_potential_profit += max(0, unrealized_pnl)
                total_potential_loss += min(0, unrealized_pnl)
            
            # Display as table
            trades_df = pd.DataFrame(trades_data)
            st.dataframe(trades_df, use_container_width=True)
            
            # Summary metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("📊 Total Open", len(open_trades))
            with col2:
                st.metric("📈 Potential Profit", f"${total_potential_profit:,.2f}", delta="Best case")
            with col3:
                st.metric("📉 Potential Loss", f"${total_potential_loss:,.2f}", delta="Worst case")
            with col4:
                total_exposure_pct = (total_exposure / st.session_state.trade_executor.balance * 100) if st.session_state.trade_executor.balance > 0 else 0
                st.metric("💰 Exposure", f"{total_exposure_pct:.1f}%", delta="Of account")
            with col5:
                net_risk = total_potential_loss if total_potential_loss < 0 else 0
                st.metric("⚠️ Total Risk", f"${abs(net_risk):,.2f}", delta="Combined risk")
        else:
            st.info("✅ No active trades running | Waiting for next signals...")

    
    # ========================================================================
    # HEADER METRICS (TradingView Style)
    # ========================================================================
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        current_price = df.iloc[-1]['close']
        st.metric("Price", f"${current_price:,.2f}", delta=f"{((df.iloc[-1]['close'] - df.iloc[-30]['close']) / df.iloc[-30]['close'] * 100):.2f}%")
    
    with col2:
        rsi = df.iloc[-1]['rsi']
        rsi_status = "🔴 Overbought" if rsi > 70 else "🟢 Oversold" if rsi < 30 else "🟡 Neutral"
        st.metric("RSI (14)", f"{rsi:.1f}", rsi_status)
    
    with col3:
        vol = df.iloc[-1]['volume']
        vol_ma = df.iloc[-1]['volume_ma']
        vol_ratio = (vol / vol_ma * 100) if vol_ma > 0 else 0
        st.metric("Volume", f"{vol:,.0f}", f"{vol_ratio:.0f}% of MA")
    
    with col4:
        bias_label = "Bullish" if combined_bias == 1 else "Bearish" if combined_bias == -1 else "Neutral"
        st.metric("HTF Bias (4H+1D)", bias_label)
    
    with col5:
        st.metric("Confluence", f"{df.iloc[-1]['fvg_confluence_score']:.0f}/100", f"Min {min_confluence_threshold}")
    
    with col6:
        if latest_prob is not None:
            prob_color = "🟢" if latest_prob > prob_threshold else "🔴"
            st.metric("FVG Probability", f"{latest_prob:.1f}%", f"{prob_color} Signal")
        else:
            st.metric("FVG Probability", "N/A", "No Signal")
    
    # ========================================================================
    # 💡 TRADE RECOMMENDATIONS - ALL TIMEFRAMES ANALYSIS
    # ========================================================================
    
    st.markdown("---")
    st.subheader("💡 Trade Recommendations - Multi-Timeframe Analysis")
    st.markdown("*Analyzing ALL timeframes to find the best trading opportunities with clear reasoning*")
    
    # Collect all recommendations from all timeframes
    all_trade_recommendations = []
    recommendation_timeframes = scan_timeframes if turbo_mode else all_timeframes
    recommendation_cache_seconds = 120 if turbo_mode else 60
    use_cached_recommendations = False

    if high_performance_mode and 'last_recommendation_scan' in st.session_state:
        rec_elapsed = (datetime.now() - st.session_state.last_recommendation_scan).total_seconds()
        cached_rec_timeframes = st.session_state.get('recommendation_timeframes_cache', all_timeframes)
        if rec_elapsed < recommendation_cache_seconds and cached_rec_timeframes == recommendation_timeframes:
            all_trade_recommendations = st.session_state.get('all_trade_recommendations_cache', [])
            use_cached_recommendations = True
    
    timeframe_weights = {
        '1w': 100,  # Highest priority
        '1d': 90,
        '4h': 80,
        '2h': 70,
        '1h': 60,
        '15m': 50,
        '5m': 40,
        '1m': 30   # Lowest priority
    }
    
    if not use_cached_recommendations:
        for tf in recommendation_timeframes:
            try:
                # Reuse data from multi-timeframe scan when available to avoid duplicate heavy processing
                df_rec = multitf_data.get(tf)

                # Adjust confluence threshold based on timeframe
                tf_conf_adjust = {
                    '1w': -25, '1d': -20, '4h': -15, '2h': -10,
                    '1h': 0, '15m': 5, '5m': 10, '1m': 15
                }
                tf_min_conf = max(20, min_confluence_threshold + tf_conf_adjust.get(tf, 0))

                if df_rec is None:
                    df_rec = fetcher.fetch_historical_data(timeframe=tf, limit=candle_limit.get(tf, 500))
                    if df_rec is None or len(df_rec) < 10:
                        continue
                    df_rec = SMCIndicators.engineer_all_features(
                        df_rec,
                        htf_bias=combined_bias,
                        min_confluence_threshold=tf_min_conf
                    )

                if len(df_rec) < 10:
                    continue

                # Get latest candle data
                latest = df_rec.iloc[-1]
                current_price = latest['close']
                fvg_type = latest.get('fvg_type', 'none')
                fvg_valid = latest.get('fvg_valid', False)
                conf_score = latest.get('fvg_confluence_score', 0)
                rsi = latest.get('rsi', 50)
                bos_bull = latest.get('bos_bullish', False)
                bos_bear = latest.get('bos_bearish', False)
                ob_bull = latest.get('order_block_bullish', False)
                ob_bear = latest.get('order_block_bearish', False)
                adx = latest.get('adx', 0)
                atr_pct = latest.get('atr_pct', 0)

                # Initialize recommendation data
                rec = {
                    'timeframe': tf,
                    'action': 'WAIT',
                    'direction': None,
                    'confidence': 'LOW',
                    'score': 0,
                    'entry': None,
                    'stop_loss': None,
                    'take_profit': None,
                    'reasons': [],
                    'warnings': []
                }

                # Signal-first recommendation: align with live trading logic so users see ENTER NOW when valid.
                signal_now = st.session_state.trade_executor.generate_signal(
                    df_rec,
                    tf,
                    confluenceThreshold=tf_min_conf
                )

                if signal_now.get('type') in ('BUY', 'SELL'):
                    rec['action'] = f"ENTER NOW ({signal_now['type']})"
                    rec['direction'] = 'LONG' if signal_now['type'] == 'BUY' else 'SHORT'
                    rec['confidence'] = 'HIGH' if conf_score >= tf_min_conf else 'MEDIUM'
                    rec['entry'] = signal_now.get('entry', current_price)
                    rec['stop_loss'] = signal_now.get('stop_loss')
                    rec['take_profit'] = signal_now.get('take_profit')
                    rec['score'] = timeframe_weights[tf] + conf_score + 20
                    rec['reasons'].append(f"🚀 **ENTER NOW**: {signal_now.get('reason', 'Valid SMC/FVG signal confirmed')}")
                    rec['reasons'].append(f"📊 **Timeframe: {tf.upper()}** | Confluence: {conf_score:.0f}/{tf_min_conf}")
                    rec['reasons'].append(f"📊 **Volatility (ATR): {atr_pct:.3f}%** | RSI: {rsi:.1f}")
                    all_trade_recommendations.append(rec)
                    continue

                if signal_now.get('blocked_reason'):
                    rec['action'] = 'WAIT (Blocked)'
                    rec['score'] = max(rec['score'], timeframe_weights[tf] * 0.2)
                    rec['reasons'].append("⏳ Setup detected but currently blocked by risk memory safeguards")
                    rec['warnings'].append(f"⚠️ {signal_now.get('blocked_reason')}")
                    all_trade_recommendations.append(rec)
                    continue

                # === BULLISH SETUP DETECTION ===
                if fvg_type == 'bullish' and fvg_valid and conf_score >= tf_min_conf:
                    if bos_bull:
                        rec['action'] = 'STRONG BUY' if combined_bias >= 0 else 'BUY'
                        rec['direction'] = 'LONG'
                        rec['confidence'] = 'HIGH' if combined_bias >= 0 else 'MEDIUM'

                        rec['entry'] = current_price
                        fvg_low = latest.get('fvg_gap_low', current_price * 0.998)
                        rec['stop_loss'] = fvg_low * 0.997
                        risk = rec['entry'] - rec['stop_loss']
                        rec['take_profit'] = rec['entry'] + (risk * 2.5)

                        rec['reasons'].append(f"✅ **Bullish FVG confirmed** with {conf_score:.0f} confluence score")
                        rec['reasons'].append(f"✅ **Bullish BOS (Break of Structure)** - momentum confirmed")

                        if combined_bias == 1:
                            rec['reasons'].append("✅ **HTF Bias is BULLISH** - aligned with higher timeframes")
                            rec['score'] = timeframe_weights[tf] + conf_score
                        elif combined_bias == 0:
                            rec['reasons'].append("⚪ **HTF Bias is NEUTRAL** - acceptable for long")
                            rec['score'] = timeframe_weights[tf] + conf_score - 10
                        else:
                            rec['warnings'].append("⚠️ **HTF Bias is BEARISH** - counter-trend trade, reduce position size")
                            rec['score'] = timeframe_weights[tf] + conf_score - 30

                        if ob_bull:
                            rec['reasons'].append("✅ **Bullish Order Block present** - strong demand zone")
                            rec['score'] += 10

                        if rsi < 50:
                            rec['reasons'].append(f"✅ **RSI at {rsi:.1f}** - room for upside movement")
                            rec['score'] += 5
                        elif rsi > 70:
                            rec['warnings'].append(f"⚠️ **RSI overbought ({rsi:.1f})** - may pullback first")
                            rec['score'] -= 10

                        if adx > 25:
                            rec['reasons'].append(f"✅ **Strong trend (ADX: {adx:.1f})** - momentum present")
                            rec['score'] += 5

                        rec['reasons'].append(f"📊 **Timeframe: {tf.upper()}** - Higher TF = Stronger signal")
                        rec['reasons'].append(f"📊 **Volatility (ATR): {atr_pct:.3f}%** - Market movement gauge")
                        all_trade_recommendations.append(rec)

                    elif conf_score >= tf_min_conf + 10:
                        rec['action'] = 'WAIT'
                        rec['reasons'].append(f"⏳ **Bullish FVG forming** ({conf_score:.0f} confluence) - waiting for BOS")
                        rec['warnings'].append("⚠️ **No BOS confirmation yet** - wait for break of structure")
                        rec['score'] = 5
                        all_trade_recommendations.append(rec)

                # === BEARISH SETUP DETECTION ===
                elif fvg_type == 'bearish' and fvg_valid and conf_score >= tf_min_conf:
                    if bos_bear:
                        rec['action'] = 'STRONG SELL' if combined_bias <= 0 else 'SELL'
                        rec['direction'] = 'SHORT'
                        rec['confidence'] = 'HIGH' if combined_bias <= 0 else 'MEDIUM'

                        rec['entry'] = current_price
                        fvg_high = latest.get('fvg_gap_high', current_price * 1.002)
                        rec['stop_loss'] = fvg_high * 1.003
                        risk = rec['stop_loss'] - rec['entry']
                        rec['take_profit'] = rec['entry'] - (risk * 2.5)

                        rec['reasons'].append(f"✅ **Bearish FVG confirmed** with {conf_score:.0f} confluence score")
                        rec['reasons'].append("✅ **Bearish BOS (Break of Structure)** - momentum confirmed")

                        if combined_bias == -1:
                            rec['reasons'].append("✅ **HTF Bias is BEARISH** - aligned with higher timeframes")
                            rec['score'] = timeframe_weights[tf] + conf_score
                        elif combined_bias == 0:
                            rec['reasons'].append("⚪ **HTF Bias is NEUTRAL** - acceptable for short")
                            rec['score'] = timeframe_weights[tf] + conf_score - 10
                        else:
                            rec['warnings'].append("⚠️ **HTF Bias is BULLISH** - counter-trend trade, reduce position size")
                            rec['score'] = timeframe_weights[tf] + conf_score - 30

                        if ob_bear:
                            rec['reasons'].append("✅ **Bearish Order Block present** - strong supply zone")
                            rec['score'] += 10

                        if rsi > 50:
                            rec['reasons'].append(f"✅ **RSI at {rsi:.1f}** - room for downside movement")
                            rec['score'] += 5
                        elif rsi < 30:
                            rec['warnings'].append(f"⚠️ **RSI oversold ({rsi:.1f})** - may bounce first")
                            rec['score'] -= 10

                        if adx > 25:
                            rec['reasons'].append(f"✅ **Strong trend (ADX: {adx:.1f})** - momentum present")
                            rec['score'] += 5

                        rec['reasons'].append(f"📊 **Timeframe: {tf.upper()}** - Higher TF = Stronger signal")
                        rec['reasons'].append(f"📊 **Volatility (ATR): {atr_pct:.3f}%** - Market movement gauge")
                        all_trade_recommendations.append(rec)

                    elif conf_score >= tf_min_conf + 10:
                        rec['action'] = 'WAIT'
                        rec['reasons'].append(f"⏳ **Bearish FVG forming** ({conf_score:.0f} confluence) - waiting for BOS")
                        rec['warnings'].append("⚠️ **No BOS confirmation yet** - wait for break of structure")
                        rec['score'] = 5
                        all_trade_recommendations.append(rec)

            except Exception:
                continue

        st.session_state.last_recommendation_scan = datetime.now()
        st.session_state.all_trade_recommendations_cache = all_trade_recommendations
        st.session_state.recommendation_timeframes_cache = recommendation_timeframes
    
    # Sort recommendations by score (highest first)
    all_trade_recommendations.sort(key=lambda x: x['score'], reverse=True)
    
    # Display top 3 recommendations
    if all_trade_recommendations:
        top_recs = all_trade_recommendations[:3]
        
        for idx, rec in enumerate(top_recs):
            with st.expander(f"**#{idx+1}: {rec['action']} - {rec['timeframe'].upper()}** (Score: {rec['score']:.0f}) | Confidence: {rec['confidence']}", expanded=(idx==0)):
                
                # Color-coded header
                if rec['action'].startswith('ENTER NOW'):
                    if 'BUY' in rec['action']:
                        st.success(f"### 🟢 {rec['action']} - {rec['timeframe'].upper()}")
                    else:
                        st.error(f"### 🔴 {rec['action']} - {rec['timeframe'].upper()}")
                elif rec['action'].startswith('STRONG BUY'):
                    st.success(f"### 🟢 {rec['action']} - {rec['timeframe'].upper()}")
                elif rec['action'].startswith('BUY'):
                    st.info(f"### 🔵 {rec['action']} - {rec['timeframe'].upper()}")
                elif rec['action'].startswith('STRONG SELL'):
                    st.error(f"### 🔴 {rec['action']} - {rec['timeframe'].upper()}")
                elif rec['action'].startswith('SELL'):
                    st.warning(f"### 🟠 {rec['action']} - {rec['timeframe'].upper()}")
                else:
                    st.info(f"### ⏳ {rec['action']} - {rec['timeframe'].upper()}")
                
                if rec['direction']:
                    # Show trade setup
                    col_setup1, col_setup2 = st.columns(2)
                    
                    with col_setup1:
                        st.markdown("#### 📊 Trade Setup")
                        st.metric("💰 Entry Price", f"${rec['entry']:,.2f}", "Current market")
                        st.metric("🛡️ Stop Loss", f"${rec['stop_loss']:,.2f}", f"${abs(rec['entry'] - rec['stop_loss']):,.2f} risk")
                        st.metric("🎯 Take Profit", f"${rec['take_profit']:,.2f}", f"${abs(rec['take_profit'] - rec['entry']):,.2f} reward")
                        
                        rr = abs(rec['take_profit'] - rec['entry']) / abs(rec['entry'] - rec['stop_loss']) if rec['stop_loss'] != rec['entry'] else 0
                        st.metric("📈 Risk:Reward", f"1:{rr:.2f}", "Per trade")
                        
                        # Position sizing (1% risk)
                        balance = st.session_state.trade_executor.balance
                        risk_amt = balance * 0.01
                        pos_size = risk_amt / abs(rec['entry'] - rec['stop_loss']) if rec['stop_loss'] != rec['entry'] else 0
                        st.metric("💼 Position Size", f"{pos_size:.4f} BTC", f"1% risk = ${risk_amt:,.2f}")
                    
                    with col_setup2:
                        st.markdown("#### 🔍 Why This Trade?")
                        for reason in rec['reasons']:
                            st.markdown(reason)
                        
                        if rec['warnings']:
                            st.markdown("#### ⚠️ Warnings")
                            for warning in rec['warnings']:
                                st.markdown(warning)
                else:
                    # Just show analysis
                    st.markdown("#### 📋 Analysis")
                    for reason in rec['reasons']:
                        st.markdown(reason)
                    if rec['warnings']:
                        for warning in rec['warnings']:
                            st.markdown(warning)
    else:
        st.warning("⏳ **No Clear Trade Setups** - Waiting for valid FVG with BOS confirmation")
        st.info(f"💡 **Current Market Conditions:**\n- HTF Bias: {'🟢 Bullish' if combined_bias == 1 else '🔴 Bearish' if combined_bias == -1 else '⚪ Neutral'}\n- Looking for: Valid FVG + Break of Structure + High Confluence\n- Min Confluence: {min_confluence_threshold}")
    
    st.markdown("---")
    
    # ========================================================================
    # MAIN CHART - TRADINGVIEW STYLE (HIGH RESOLUTION WITH ZOOM)
    # ========================================================================
    
    st.subheader(f"📊 {selected_timeframe.upper()} Candlestick Chart - BTC/USDT (INTERACTIVE)")
    
    # Create subplots with candlestick + volume + RSI
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=("Price Action | Zoom & Pan with Mouse", "Volume Analysis", "RSI Momentum")
    )
    
    # -------- CANDLESTICK CHART (LARGER & THICKER) --------
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='BTC/USDT',
        showlegend=True,
        increasing=dict(fillcolor='#00ff41', line=dict(color='#00ff41', width=2)),
        decreasing=dict(fillcolor='#ff0000', line=dict(color='#ff0000', width=2))
    ), row=1, col=1)
    
    # ========================================================================
    # SUPPORT & RESISTANCE ZONES (FILTERED BY VIEW MODE)
    # ========================================================================
    if show_swing:
        if show_all_timeframes:
            # Show ALL timeframes zones
            with st.spinner("🔍 Analyzing multi-timeframe zones..."):
                mtf_zones = SMCIndicators.get_mtf_support_resistance(fetcher)
            
            # Draw all MTF zones (higher timeframe zones drawn first = more prominent)
            for zone in mtf_zones:
                # Draw zone rectangle from pivot point to end of chart
                fig.add_shape(
                    type="rect",
                    x0=zone['timestamp'],
                    x1=df['timestamp'].iloc[-1],
                    y0=zone['zone_low'],
                    y1=zone['zone_high'],
                    fillcolor=zone['color'],
                    opacity=zone['opacity'],
                    layer="below",
                    line=dict(color=zone['color'], width=zone['line_width']),
                    row=1,
                    col=1
                )
                
                # Add pivot marker with timeframe label
                marker_symbol = 'diamond' if zone['type'] == 'support' else 'diamond'
                marker_color = zone['color']
                
                fig.add_scatter(
                    x=[zone['timestamp']],
                    y=[zone['price']],
                    mode='markers+text',
                    marker=dict(size=10, color=marker_color, symbol=marker_symbol, 
                               line=dict(width=2, color='white')),
                    text=zone['timeframe'],
                    textposition='middle right' if zone['type'] == 'support' else 'middle right',
                    textfont=dict(size=9, color='white', family='monospace'),
                    name=f"{zone['timeframe']} {zone['type'].title()}",
                    showlegend=False,
                    row=1,
                    col=1
                )
            
            st.info(f"🎯 **Multi-Timeframe Mode**: Showing {len(mtf_zones)} zones from 1w, 1d, 4h, 2h, 1h, 15m, 5m, 1m | Higher timeframe = Stronger")
        
        else:
            # Show ONLY current timeframe zones
            df_current = df.copy()
            df_current = SMCIndicators.calculate_swing_points(df_current)
            df_current = SMCIndicators.calculate_atr_adx(df_current)
            
            swing_lows = df_current[df_current['is_swing_low']].copy()
            swing_highs = df_current[df_current['is_swing_high']].copy()
            
            # Select top 5 strongest pivots from recent 15
            if len(swing_lows) > 0:
                recent_lows = swing_lows.tail(15).nlargest(5, 'swing_low_strength')
            else:
                recent_lows = pd.DataFrame()
            
            if len(swing_highs) > 0:
                recent_highs = swing_highs.tail(15).nlargest(5, 'swing_high_strength')
            else:
                recent_highs = pd.DataFrame()
            
            # Draw support zones (white) from pivot forward
            for idx, sr in recent_lows.iterrows():
                zone_half = (sr['atr'] * 0.25) if pd.notna(sr.get('atr')) and sr.get('atr', 0) > 0 else sr['close'] * 0.0022
                price = sr['low']
                pivot_time = sr['timestamp']
                
                fig.add_shape(
                    type="rect",
                    x0=pivot_time,
                    x1=df['timestamp'].iloc[-1],
                    y0=price - zone_half,
                    y1=price + zone_half,
                    fillcolor="white",
                    opacity=0.20,
                    layer="below",
                    line=dict(color='cyan', width=1.5),
                    row=1,
                    col=1
                )
                
                # Add pivot marker
                fig.add_scatter(
                    x=[pivot_time],
                    y=[price],
                    mode='markers',
                    marker=dict(size=9, color='white', symbol='diamond', line=dict(width=2, color='cyan')),
                    name='Support Pivot',
                    showlegend=False,
                    row=1,
                    col=1
                )
            
            # Draw resistance zones (purple/magenta) from pivot forward
            for idx, sr in recent_highs.iterrows():
                zone_half = (sr['atr'] * 0.25) if pd.notna(sr.get('atr')) and sr.get('atr', 0) > 0 else sr['close'] * 0.0022
                price = sr['high']
                pivot_time = sr['timestamp']
                
                fig.add_shape(
                    type="rect",
                    x0=pivot_time,
                    x1=df['timestamp'].iloc[-1],
                    y0=price - zone_half,
                    y1=price + zone_half,
                    fillcolor="purple",
                    opacity=0.22,
                    layer="below",
                    line=dict(color='magenta', width=1.5),
                    row=1,
                    col=1
                )
                
                # Add pivot marker
                fig.add_scatter(
                    x=[pivot_time],
                    y=[price],
                    mode='markers',
                    marker=dict(size=9, color='magenta', symbol='diamond', line=dict(width=2, color='purple')),
                    name='Resistance Pivot',
                    showlegend=False,
                    row=1,
                    col=1
                )
            
            zone_count = len(recent_lows) + len(recent_highs)
            st.info(f"🎯 **Single Timeframe Mode ({selected_timeframe.upper()})**: Showing {zone_count} zones - Support (white) & Resistance (purple)")
    
    
    # Add SMA 20
    if len(df) >= 20:
        df['sma20'] = df['close'].rolling(window=20).mean()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['sma20'],
            mode='lines', name='SMA 20',
            line=dict(color='#FFD700', width=2),
            showlegend=True
        ), row=1, col=1)
    
    # Add SMA 50
    if len(df) >= 50:
        df['sma50'] = df['close'].rolling(window=50).mean()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['sma50'],
            mode='lines', name='SMA 50',
            line=dict(color='#FF6B6B', width=2),
            showlegend=True
        ), row=1, col=1)
    
    # -------- BULLISH FAIR VALUE GAPS (GREEN RECTANGLES) --------
    if show_fvg:
        for idx in df[(df['fvg_type'] == 'bullish') & (df['fvg_valid'])].index[-20:]:
            if idx >= 2 and pd.notna(df.loc[idx, 'fvg_lower']) and pd.notna(df.loc[idx, 'fvg_upper']):
                fvg_low = df.loc[idx, 'fvg_lower']
                fvg_high = df.loc[idx, 'fvg_upper']
                fig.add_shape(
                    type="rect",
                    x0=df.loc[idx-2, 'timestamp'],
                    x1=df.loc[idx, 'timestamp'],
                    y0=fvg_low,
                    y1=fvg_high,
                    fillcolor="green",
                    opacity=0.25,
                    layer="below",
                    line=dict(color='green', width=2),
                    row=1, col=1
                )
                mid_time = df.loc[idx-1, 'timestamp']
                mid_price = (fvg_low + fvg_high) / 2
                fig.add_annotation(
                    x=mid_time,
                    y=mid_price,
                    text="📈 BULLISH FVG",
                    showarrow=False,
                    font=dict(size=10, color='#00ff41'),
                    bgcolor='rgba(0,255,65,0.3)',
                    bordercolor='green',
                    borderwidth=1,
                    row=1, col=1
                )
    
    # -------- BEARISH FAIR VALUE GAPS (RED RECTANGLES) --------
    if show_fvg:
        for idx in df[(df['fvg_type'] == 'bearish') & (df['fvg_valid'])].index[-20:]:
            if idx >= 2 and pd.notna(df.loc[idx, 'fvg_lower']) and pd.notna(df.loc[idx, 'fvg_upper']):
                fvg_low = df.loc[idx, 'fvg_lower']
                fvg_high = df.loc[idx, 'fvg_upper']
                fig.add_shape(
                    type="rect",
                    x0=df.loc[idx-2, 'timestamp'],
                    x1=df.loc[idx, 'timestamp'],
                    y0=fvg_low,
                    y1=fvg_high,
                    fillcolor="red",
                    opacity=0.25,
                    layer="below",
                    line=dict(color='red', width=2),
                    row=1, col=1
                )

        # Rejected FVG zones (blocked by nearby support/resistance)
        for idx in df[(df['fvg_type'] != 'none') & (~df['fvg_valid'])].index[-15:]:
            if idx >= 2:
                if pd.isna(df.loc[idx, 'fvg_lower']) or pd.isna(df.loc[idx, 'fvg_upper']):
                    continue
                zone_low = df.loc[idx, 'fvg_lower']
                zone_high = df.loc[idx, 'fvg_upper']

                fig.add_shape(
                    type="rect",
                    x0=df.loc[idx-2, 'timestamp'],
                    x1=df.loc[idx, 'timestamp'],
                    y0=min(zone_low, zone_high),
                    y1=max(zone_low, zone_high),
                    fillcolor="#808080",
                    opacity=0.10,
                    layer="below",
                    line=dict(color='#9a9a9a', width=1, dash='dot'),
                    row=1, col=1
                )
                mid_time = df.loc[idx-1, 'timestamp']
                mid_price = (min(zone_low, zone_high) + max(zone_low, zone_high)) / 2
                fig.add_annotation(
                    x=mid_time,
                    y=mid_price,
                    text=f"REJECTED ({int(df.loc[idx, 'fvg_confluence_score'])})",
                    showarrow=False,
                    font=dict(size=9, color=THEME_TEXT),
                    bgcolor='rgba(80,80,80,0.3)',
                    bordercolor='#9a9a9a',
                    borderwidth=1,
                    row=1, col=1
                )
    
    # -------- BREAK OF STRUCTURE / CHOCH --------
    if show_bos:
        bos_bullish = df[df['bos_bullish']].index[-15:]
        for i, idx in enumerate(bos_bullish):
            fig.add_scatter(
                x=[df.loc[idx, 'timestamp']],
                y=[df.loc[idx, 'close']],
                mode='markers',
                marker=dict(size=15, color='lime', symbol='triangle-up', 
                           line=dict(width=3, color='darkgreen')),
                name='Bullish BOS',
                showlegend=(i == 0),
                row=1, col=1
            )

        choch_bullish = df[df['choch_bullish']].index[-10:]
        for i, idx in enumerate(choch_bullish):
            fig.add_scatter(
                x=[df.loc[idx, 'timestamp']],
                y=[df.loc[idx, 'close']],
                mode='markers',
                marker=dict(size=14, color='#7CFC00', symbol='star', line=dict(width=2, color='green')),
                name='Bullish ChoCh',
                showlegend=(i == 0),
                row=1,
                col=1
            )
        
        bos_bearish = df[df['bos_bearish']].index[-15:]
        for i, idx in enumerate(bos_bearish):
            fig.add_scatter(
                x=[df.loc[idx, 'timestamp']],
                y=[df.loc[idx, 'close']],
                mode='markers',
                marker=dict(size=15, color='#ff3333', symbol='triangle-down', 
                           line=dict(width=3, color='darkred')),
                name='Bearish BOS',
                showlegend=(i == 0),
                row=1, col=1
            )

        choch_bearish = df[df['choch_bearish']].index[-10:]
        for i, idx in enumerate(choch_bearish):
            fig.add_scatter(
                x=[df.loc[idx, 'timestamp']],
                y=[df.loc[idx, 'close']],
                mode='markers',
                marker=dict(size=14, color='#ff7f7f', symbol='star', line=dict(width=2, color='darkred')),
                name='Bearish ChoCh',
                showlegend=(i == 0),
                row=1,
                col=1
            )
    
    # -------- ORDER BLOCKS (INSTITUTIONAL ZONES) --------
    if show_bos:  # Using same toggle as BOS/ChoCh for SMC structures
        # Bullish Order Blocks (blue zones)
        ob_bullish_indices = df[df['ob_bullish']].index[-10:]
        for idx in ob_bullish_indices:
            if pd.notna(df.loc[idx, 'ob_high']) and pd.notna(df.loc[idx, 'ob_low']):
                ob_start = df.loc[idx, 'timestamp']
                ob_end = df['timestamp'].iloc[-1]  # Extend to current time
                
                fig.add_shape(
                    type="rect",
                    x0=ob_start,
                    x1=ob_end,
                    y0=df.loc[idx, 'ob_low'],
                    y1=df.loc[idx, 'ob_high'],
                    fillcolor="#1E90FF",
                    opacity=0.15,
                    layer="below",
                    line=dict(color='#1E90FF', width=2, dash='dot'),
                    row=1,
                    col=1
                )
                
                # Add label
                mid_price = (df.loc[idx, 'ob_low'] + df.loc[idx, 'ob_high']) / 2
                fig.add_annotation(
                    x=ob_start,
                    y=mid_price,
                    text=f"🔵 BULL OB",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor='#1E90FF',
                    ax=40,
                    ay=-20,
                    font=dict(size=9, color='#1E90FF', family='monospace'),
                    bgcolor='rgba(30,144,255,0.3)',
                    bordercolor='#1E90FF',
                    borderwidth=1,
                    row=1,
                    col=1
                )
        
        # Bearish Order Blocks (orange zones)
        ob_bearish_indices = df[df['ob_bearish']].index[-10:]
        for idx in ob_bearish_indices:
            if pd.notna(df.loc[idx, 'ob_high']) and pd.notna(df.loc[idx, 'ob_low']):
                ob_start = df.loc[idx, 'timestamp']
                ob_end = df['timestamp'].iloc[-1]  # Extend to current time
                
                fig.add_shape(
                    type="rect",
                    x0=ob_start,
                    x1=ob_end,
                    y0=df.loc[idx, 'ob_low'],
                    y1=df.loc[idx, 'ob_high'],
                    fillcolor="#FF8C00",
                    opacity=0.15,
                    layer="below",
                    line=dict(color='#FF8C00', width=2, dash='dot'),
                    row=1,
                    col=1
                )
                
                # Add label
                mid_price = (df.loc[idx, 'ob_low'] + df.loc[idx, 'ob_high']) / 2
                fig.add_annotation(
                    x=ob_start,
                    y=mid_price,
                    text=f"🔶 BEAR OB",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor='#FF8C00',
                    ax=40,
                    ay=20,
                    font=dict(size=9, color='#FF8C00', family='monospace'),
                    bgcolor='rgba(255,140,0,0.3)',
                    bordercolor='#FF8C00',
                    borderwidth=1,
                    row=1,
                    col=1
                )
    
    # -------- VOLUME BARS (COLOR CODED) --------
    colors = ['#ff0000' if close <= open_ else '#00ff41' 
              for close, open_ in zip(df['close'], df['open'])]
    
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['volume'],
        name='Volume',
        marker=dict(color=colors),
        showlegend=True
    ), row=2, col=1)
    
    # Volume MA
    if len(df) >= 20:
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['volume_ma'],
            mode='lines', name='Volume MA (20)',
            line=dict(color='#FFD700', width=3),
            showlegend=True
        ), row=2, col=1)
    
    # -------- RSI INDICATOR (FULL CLARITY) --------
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['rsi'],
        mode='lines', name='RSI (14)',
        line=dict(color='#00D4FF', width=3),
        fill='tozeroy',
        fillcolor='rgba(0,212,255,0.2)',
        showlegend=True
    ), row=3, col=1)
    
    fig.add_hline(y=70, line_dash="dash", line_color="red", line_width=2, annotation_text="Overbought (70)", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", line_width=2, annotation_text="Oversold (30)", row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="gray", line_width=1, row=3, col=1)
    
    # -------- UPDATE LAYOUT FOR MAXIMUM CLARITY & ZOOMING --------
    fig.update_layout(
        title=dict(
            text=f"<b>BTC/USDT {selected_timeframe.upper()}</b> | Real-Time Smart Money Concepts Analysis",
            font=dict(size=18, color=THEME_TEXT)
        ),
        height=1200 if high_performance_mode else 1600,
        hovermode='x unified',
        margin=dict(l=100, r=100, t=120, b=100),
        plot_bgcolor=THEME_BG,
        paper_bgcolor=THEME_BG,
        font=dict(color=THEME_TEXT, family='sans-serif', size=12),
        xaxis_rangeslider_visible=False,
        dragmode='zoom',  # Enable zoom mode
        showlegend=True,
        legend=dict(
            x=0.01,
            y=0.99,
            bgcolor='rgba(255,249,240,0.95)',
            bordercolor=THEME_BORDER,
            borderwidth=2
        )
    )
    
    # Update axes for ALL subplots
    fig.update_xaxes(
        gridcolor=THEME_GRID,
        showgrid=True,
        zeroline=False,
        showline=True,
        linewidth=2,
        linecolor=THEME_BORDER,
        rangeselector=dict(visible=False)
    )
    
    fig.update_yaxes(
        gridcolor=THEME_GRID,
        showgrid=True,
        zeroline=False,
        showline=True,
        linewidth=2,
        linecolor=THEME_BORDER,
        automargin=True
    )
    
    # ========================================================================
    # HIGHLIGHT SELECTED TRADE ON CHART
    # ========================================================================
    if 'highlighted_trade' in st.session_state and st.session_state.highlighted_trade:
        trade = st.session_state.highlighted_trade
        
        # Find the entry candle in the current dataframe
        entry_time_str = str(trade['entry_time'])
        try:
            # Try to find matching timestamp
            entry_df = df[df['timestamp'].astype(str).str.contains(entry_time_str[:16])]  # Match up to minute
            
            if not entry_df.empty:
                entry_candle = entry_df.iloc[0]
                entry_timestamp = entry_candle['timestamp']
                
                # Add Entry Price Line (dashed)
                fig.add_hline(
                    y=trade['entry_price'],
                    line_dash="dash",
                    line_color="blue" if trade['direction'] == 'BUY' else "orange",
                    line_width=3,
                    annotation_text=f"📍 Entry: ${trade['entry_price']:,.2f}",
                    annotation_position="right",
                    row=1, col=1
                )
                
                # Add Take Profit Line (green)
                fig.add_hline(
                    y=trade['tp'],
                    line_dash="solid",
                    line_color="green",
                    line_width=3,
                    annotation_text=f"🎯 TP: ${trade['tp']:,.2f}",
                    annotation_position="right",
                    row=1, col=1
                )
                
                # Add Stop Loss Line (red)
                fig.add_hline(
                    y=trade['sl'],
                    line_dash="solid",
                    line_color="red",
                    line_width=3,
                    annotation_text=f"🛑 SL: ${trade['sl']:,.2f}",
                    annotation_position="right",
                    row=1, col=1
                )
                
                # Add Entry Marker (Large Arrow)
                marker_symbol = 'triangle-up' if trade['direction'] == 'BUY' else 'triangle-down'
                marker_color = '#00ff41' if trade['direction'] == 'BUY' else '#ff0000'
                marker_y = entry_candle['low'] * 0.998 if trade['direction'] == 'BUY' else entry_candle['high'] * 1.002
                
                fig.add_trace(go.Scatter(
                    x=[entry_timestamp],
                    y=[marker_y],
                    mode='markers+text',
                    marker=dict(
                        size=25,
                        color=marker_color,
                        symbol=marker_symbol,
                        line=dict(width=3, color='white')
                    ),
                    text=f"ENTRY<br>{trade['direction']}",
                    textposition='top center' if trade['direction'] == 'BUY' else 'bottom center',
                    textfont=dict(size=12, color='white', family='monospace'),
                    name=f"Trade #{trade['trade_id']} Entry",
                    showlegend=True,
                    hovertemplate=f"<b>Trade #{trade['trade_id']}</b><br>" +
                                  f"Entry: ${trade['entry_price']:,.2f}<br>" +
                                  f"TP: ${trade['tp']:,.2f}<br>" +
                                  f"SL: ${trade['sl']:,.2f}<br>" +
                                  f"Reason: {trade['entry_reason']}<extra></extra>"
                ), row=1, col=1)
                
                # Add vertical line at entry time
                fig.add_vline(
                    x=entry_timestamp,
                    line_dash="dot",
                    line_color=marker_color,
                    line_width=2,
                    opacity=0.5,
                    row=1, col=1
                )
                
        except Exception as e:
            st.warning(f"⚠️ Could not highlight trade on chart: {str(e)}")
    
    # Display main chart with FULL WIDTH and LARGE HEIGHT for zoom capability
    chart_config = (
        {'scrollZoom': False, 'displayModeBar': False}
        if high_performance_mode
        else {'scrollZoom': True, 'displayModeBar': True, 'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape']}
    )
    st.plotly_chart(fig, use_container_width=True, config=chart_config)
    
    # ========================================================================
    # TRADE PERFORMANCE CHARTS
    # ========================================================================
    
    st.markdown("---")
    st.subheader("📈 Trade Performance Analysis")
    all_trades = st.session_state.trade_executor.trade_memory.get_recent_trades(limit=100)
    if high_performance_mode:
        st.info("⚡ High Performance Mode: detailed performance charts are minimized for faster interactions.")
    
    if (not high_performance_mode) and all_trades:
        # Create performance subplots
        perf_col1, perf_col2 = st.columns(2)
        
        # ---- EQUITY CURVE ----
        with perf_col1:
            if all_trades:
                equity_data = []
                cumulative_pnl = 0
                for trade in all_trades:
                    trade_id, tf, entry_time, entry_price, sl, tp, exit_time, exit_price, pnl, pnl_pct, result = trade
                    cumulative_pnl += pnl
                    equity_data.append({
                        'timestamp': exit_time,
                        'equity': st.session_state.trade_executor.balance - cumulative_pnl,
                        'cumulative_pnl': cumulative_pnl
                    })
                
                if equity_data:
                    equity_df = pd.DataFrame(equity_data)
                    equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
                    
                    fig_equity = go.Figure()
                    
                    # Initial balance line
                    fig_equity.add_hline(y=10000, line_dash="dash", line_color="gray", 
                                        line_width=1, annotation_text="Initial (10000$)")
                    
                    # Equity curve
                    fig_equity.add_trace(go.Scatter(
                        x=equity_df['timestamp'],
                        y=equity_df['equity'],
                        mode='lines',
                        name='Account Equity',
                        line=dict(color='#00ff41', width=3),
                        fill='tozeroy',
                        fillcolor='rgba(0,255,65,0.2)'
                    ))
                    
                    fig_equity.update_layout(
                        title='Account Equity Curve',
                        xaxis_title='Trade Exit Time',
                        yaxis_title='Equity ($)',
                        plot_bgcolor=THEME_BG,
                        paper_bgcolor=THEME_BG,
                        font=dict(color=THEME_TEXT, family='sans-serif'),
                        hovermode='x unified',
                        height=450
                    )
                    fig_equity.update_xaxes(gridcolor=THEME_GRID)
                    fig_equity.update_yaxes(gridcolor=THEME_GRID)
                    
                    st.plotly_chart(fig_equity, use_container_width=True)
        
        # ---- WIN/LOSS DISTRIBUTION ----
        with perf_col2:
            win_loss = {'WIN': 0, 'LOSS': 0, 'CLOSED': 0}
            pnl_values = []
            for trade in all_trades:
                result = trade[10]
                win_loss[result] += 1
                pnl_values.append(trade[8])
            
            fig_distribution = go.Figure(data=[
                go.Bar(
                    x=['Wins', 'Losses', 'Closed'],
                    y=[win_loss['WIN'], win_loss['LOSS'], win_loss['CLOSED']],
                    marker=dict(color=['#00ff41', '#ff0000', '#ffa500']),
                    text=[win_loss['WIN'], win_loss['LOSS'], win_loss['CLOSED']],
                    textposition='auto',
                )
            ])
            
            fig_distribution.update_layout(
                title='Trade Results Distribution',
                xaxis_title='Result Type',
                yaxis_title='Count',
                plot_bgcolor=THEME_BG,
                paper_bgcolor=THEME_BG,
                font=dict(color=THEME_TEXT, family='sans-serif'),
                height=450
            )
            fig_distribution.update_xaxes(gridcolor=THEME_GRID)
            fig_distribution.update_yaxes(gridcolor=THEME_GRID)
            
            st.plotly_chart(fig_distribution, use_container_width=True)
        
        # ---- P&L DISTRIBUTION ----
        perf_col3, perf_col4 = st.columns(2)
        
        with perf_col3:
            fig_pnl = go.Figure()
            
            fig_pnl.add_trace(go.Histogram(
                x=pnl_values,
                name='P&L Distribution',
                marker_color='#00D4FF',
                nbinsx=20
            ))
            
            fig_pnl.add_vline(x=0, line_dash="dash", line_color="white")
            
            fig_pnl.update_layout(
                title='P&L Distribution Histogram',
                xaxis_title='P&L ($)',
                yaxis_title='Frequency',
                plot_bgcolor=THEME_BG,
                paper_bgcolor=THEME_BG,
                font=dict(color=THEME_TEXT, family='sans-serif'),
                hovermode='x unified',
                height=450
            )
            fig_pnl.update_yaxes(gridcolor=THEME_GRID)
            fig_pnl.update_xaxes(gridcolor=THEME_GRID)
            
            st.plotly_chart(fig_pnl, use_container_width=True)
        
        # ---- CUMULATIVE P&L ----
        with perf_col4:
            cumulative_data = []
            cum = 0
            for trade in all_trades:
                cum += trade[8]
                cumulative_data.append({
                    'trade_num': len(cumulative_data) + 1,
                    'cumulative_pnl': cum,
                    'result': trade[10]
                })
            
            cum_df = pd.DataFrame(cumulative_data)
            colors = ['#00ff41' if row['result'] == 'WIN' else '#ff0000' for _, row in cum_df.iterrows()]
            
            fig_cum = go.Figure()
            
            fig_cum.add_trace(go.Bar(
                x=cum_df['trade_num'],
                y=cum_df['cumulative_pnl'],
                marker=dict(color=colors),
                name='Cumulative P&L',
                text=cum_df['cumulative_pnl'].apply(lambda x: f'${x:.0f}'),
                textposition='outside'
            ))
            
            fig_cum.add_hline(y=0, line_dash="dash", line_color="white")
            
            fig_cum.update_layout(
                title='Cumulative P&L by Trade',
                xaxis_title='Trade Number',
                yaxis_title='Cumulative P&L ($)',
                plot_bgcolor=THEME_BG,
                paper_bgcolor=THEME_BG,
                font=dict(color=THEME_TEXT, family='sans-serif'),
                height=450
            )
            fig_cum.update_xaxes(gridcolor=THEME_GRID)
            fig_cum.update_yaxes(gridcolor=THEME_GRID)
            
            st.plotly_chart(fig_cum, use_container_width=True)
    else:
        st.info("📊 No closed trades yet. Performance charts will appear after first trades close.")
    
    # ========================================================================
    # DETAILED ANALYSIS TABS
    # ========================================================================
    
    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(["📋 FVG Analysis", "📊 Indicators", "🎯 Statistics", "🤖 Model Info"])
    
    with tab1:
        st.markdown("### Recent Fair Value Gaps (FVG) - 30 Latest")
        fvg_data = []
        for idx in df[df['fvg_bullish'] | df['fvg_bearish']].index[-30:]:
            fvg_entry = {
                'Time': df.loc[idx, 'timestamp'].strftime('%Y-%m-%d %H:%M'),
                'Type': '📈 Bullish' if df.loc[idx, 'fvg_type'] == 'bullish' else '📉 Bearish',
                'Valid': '✅' if bool(df.loc[idx, 'fvg_valid']) else '❌',
                'Reason': df.loc[idx, 'fvg_invalid_reason'] if not bool(df.loc[idx, 'fvg_valid']) else 'Pass',
                'Confluence': f"{df.loc[idx, 'fvg_confluence_score']:.0f}",
                'HTF Bias': int(df.loc[idx, 'htf_bias']) if pd.notna(df.loc[idx, 'htf_bias']) else 0,
                'ATR%': f"{df.loc[idx, 'atr_pct']:.2f}" if pd.notna(df.loc[idx, 'atr_pct']) else 'NA',
                'ADX': f"{df.loc[idx, 'adx']:.1f}" if pd.notna(df.loc[idx, 'adx']) else 'NA',
                'Size (USDT)': f"{df.loc[idx, 'fvg_size']:.2f}",
                'RSI': f"{df.loc[idx, 'rsi']:.1f}",
                'Dist→Res %': f"{df.loc[idx, 'distance_to_resistance_pct']:.2f}" if pd.notna(df.loc[idx, 'distance_to_resistance_pct']) else 'NA',
                'Dist→Sup %': f"{df.loc[idx, 'distance_to_support_pct']:.2f}" if pd.notna(df.loc[idx, 'distance_to_support_pct']) else 'NA',
                'Volume': f"{df.loc[idx, 'volume']:,.0f}"
            }
            fvg_data.append(fvg_entry)
        
        if fvg_data:
            st.dataframe(pd.DataFrame(fvg_data), use_container_width=True)
        else:
            st.info("No FVGs detected in recent data")
    
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(
                x=df['timestamp'], y=df['rsi'],
                mode='lines+markers', name='RSI (14)',
                line=dict(color='#00D4FF', width=2),
                fill='tozeroy'
            ))
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
            fig_rsi.update_layout(
                title='RSI-14 Indicator',
                height=400,
                plot_bgcolor=THEME_BG,
                paper_bgcolor=THEME_BG,
                font=dict(color=THEME_TEXT)
            )
            fig_rsi.update_xaxes(gridcolor=THEME_GRID)
            fig_rsi.update_yaxes(gridcolor=THEME_GRID)
            st.plotly_chart(fig_rsi, use_container_width=True)
        
        with col2:
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=df['timestamp'], y=df['volume'],
                name='Volume', marker=dict(color='#FFD700')
            ))
            fig_vol.add_trace(go.Scatter(
                x=df['timestamp'], y=df['volume_ma'],
                mode='lines', name='Volume MA (20)',
                line=dict(color='red', width=2)
            ))
            fig_vol.update_layout(
                title='Volume Analysis',
                height=400,
                plot_bgcolor=THEME_BG,
                paper_bgcolor=THEME_BG,
                font=dict(color=THEME_TEXT)
            )
            fig_vol.update_xaxes(gridcolor=THEME_GRID)
            fig_vol.update_yaxes(gridcolor=THEME_GRID)
            st.plotly_chart(fig_vol, use_container_width=True)
    
    with tab3:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Current Price", f"${df.iloc[-1]['close']:,.2f}")
            st.metric("High (Last 50)", f"${df.tail(50)['high'].max():,.2f}")
            st.metric("Low (Last 50)", f"${df.tail(50)['low'].min():,.2f}")
        
        with col2:
            st.metric("Avg Volume", f"{df['volume'].mean():,.0f}")
            st.metric("Current Volume", f"{df.iloc[-1]['volume']:,.0f}")
            st.metric("RSI", f"{df.iloc[-1]['rsi']:.1f}")
        
        with col3:
            fvg_count = len(df[df['fvg_bullish'] | df['fvg_bearish']])
            fvg_valid_count = len(df[(df['fvg_bullish'] | df['fvg_bearish']) & (df['fvg_valid'])])
            avg_conf = df.loc[df['fvg_bullish'] | df['fvg_bearish'], 'fvg_confluence_score'].mean()
            bos_count = len(df[df['bos_bullish'] | df['bos_bearish']])
            st.metric("Total FVGs", fvg_count)
            st.metric("Valid FVGs", fvg_valid_count)
            st.metric("Avg Confluence", f"{0 if pd.isna(avg_conf) else avg_conf:.1f}")
            st.metric("Total BOS", bos_count)
            db_samples = st.session_state.trend_db.load_training_samples()
            st.metric("Trend DB Samples", len(db_samples))
    
    with tab4:
        st.markdown("### Machine Learning Model Information")
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"""
            **Model Type:** Random Forest Classifier
            **Estimators:** 100 trees
            **Max Depth:** 10
            **Training Status:** {'✅ Trained' if st.session_state.predictor.is_trained else '❌ Not Trained'}
            
            **🧠 Auto-Learning:** Enabled
            Model improves from every closed trade!
            """)
        
        with col2:
            # Show learning statistics if model has learned from trades
            if hasattr(st.session_state.predictor, 'winning_confluence'):
                st.success(f"""
                **📊 Learning from Closed Trades:**
                
                **Winning Signal Patterns:**
                - Avg Confluence: {st.session_state.predictor.winning_confluence:.1f}
                - RSI Range: {st.session_state.predictor.winning_rsi_range[0]:.0f} - {st.session_state.predictor.winning_rsi_range[1]:.0f}
                
                **Losing Signal Patterns:**
                - Avg Confluence: {st.session_state.predictor.losing_confluence:.1f}
                - RSI Range: {st.session_state.predictor.losing_rsi_range[0]:.0f} - {st.session_state.predictor.losing_rsi_range[1]:.0f}
                
                **Adaptive Confluence Threshold:** {st.session_state.predictor.get_adaptive_confluence_threshold()}
                (Auto-adjusted based on win patterns)
                """)
            else:
                st.info(f"""
                **Features Used:**
                - FVG Size, RSI, Hour, Volume
                - EMA/Trend Slopes/Volatility
                - ATR%, ADX, HTF Bias
                - Liquidity Sweep & Displacement
                - Premium/Discount Context
                - Confluence Score
                
                ⏳ **Waiting for trades** to start learning...
                """)
    
    # ========================================================================
    # TRADING DASHBOARD (TRADES & STATISTICS)
    # ========================================================================
    
    st.markdown("---")
    st.subheader("📊 Trading Dashboard")
    
    # Show open trades
    open_trades = st.session_state.trade_executor.trade_memory.get_open_trades()
    
    if open_trades:
        st.write("**🔓 OPEN TRADES:**")
        open_df = pd.DataFrame(
            open_trades,
            columns=['Trade ID', 'Timeframe', 'Entry Time', 'Entry Price', 'Stop Loss', 
                    'Take Profit', 'Risk', 'Reward', 'Confluence', 'RSI', 'FVG Type', 'Direction', 'Entry Reason']
        )
        open_df['Entry Price'] = open_df['Entry Price'].apply(lambda x: f"${x:,.2f}")
        open_df['Stop Loss'] = open_df['Stop Loss'].apply(lambda x: f"${x:,.2f}")
        open_df['Take Profit'] = open_df['Take Profit'].apply(lambda x: f"${x:,.2f}")
        open_df['Risk'] = open_df['Risk'].apply(lambda x: f"${x:,.2f}")
        open_df['Reward'] = open_df['Reward'].apply(lambda x: f"${x:,.2f}")
        open_df['Confluence'] = open_df['Confluence'].apply(lambda x: f"{x:.0f}")
        open_df['RSI'] = open_df['RSI'].apply(lambda x: f"{x:.1f}")
        open_df['Entry Reason'] = open_df['Entry Reason'].fillna('SMC/FVG signal')
        st.dataframe(open_df, use_container_width=True)
    else:
        st.info("✅ No open trades")
    
    # Show trading statistics per timeframe
    st.write("**📈 TRADE STATISTICS BY TIMEFRAME:**")
    
    tf_list = ['1w', '1d', '4h', '2h', '1h', '15m', '5m', '1m']
    stats_data = []
    total_pnl = 0
    
    for tf in tf_list:
        stats = st.session_state.trade_executor.trade_memory.get_stats(tf)
        if stats and stats['total'] > 0:
            stats_data.append({
                'Timeframe': tf.upper(),
                'Total Trades': int(stats['total']),
                'Wins': int(stats['wins']),
                'Losses': int(stats['losses']),
                'Win Rate': f"{stats['win_rate']:.1f}%",
                'Profit Factor': f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞",
                'Total P&L': f"${stats['total_pnl']:,.2f}",
                'Avg Win': f"${stats['avg_win']:,.2f}" if stats['avg_win'] > 0 else "$0.00",
                'Avg Loss': f"${stats['avg_loss']:,.2f}" if stats['avg_loss'] > 0 else "$0.00"
            })
            total_pnl += stats['total_pnl']
    
    if stats_data:
        stats_df = pd.DataFrame(stats_data)
        st.dataframe(stats_df, use_container_width=True)
        
        # Summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total P&L", f"${total_pnl:,.2f}", 
                     delta="📈 Profit" if total_pnl > 0 else "📉 Loss")
        with col2:
            st.metric("Account Equity", f"${st.session_state.trade_executor.equity:,.2f}")
        with col3:
            total_trades_all = sum(s['total'] for s in [st.session_state.trade_executor.trade_memory.get_stats(tf) for tf in tf_list if st.session_state.trade_executor.trade_memory.get_stats(tf)]) or 0
            st.metric("Total Trades", int(total_trades_all))
        with col4:
            st.metric("Risk Per Trade", "2% of Account")
    else:
        st.info("📝 No trades executed yet. System is monitoring for signals...")
    
    # Show recent closed trades separated by outcome with confidence/explanation.
    win_trades = st.session_state.trade_executor.trade_memory.get_closed_trades_by_result('WIN', limit=15)
    loss_trades = st.session_state.trade_executor.trade_memory.get_closed_trades_by_result('LOSS', limit=15)

    if win_trades or loss_trades:
        st.write("**📋 CLOSED TRADES (SEPARATED):**")

        if win_trades:
            st.success(f"🟢 WINNING TRADES ({len(win_trades)})")
            wins_df = pd.DataFrame(
                win_trades,
                columns=[
                    'Trade ID', 'TF', 'Entry Time', 'Entry', 'SL', 'TP', 'Exit Time', 'Exit',
                    'P&L', 'P&L %', 'Result', 'Direction', 'Confluence', 'RSI', 'HTF Bias',
                    'FVG Type', 'Close Reason', 'Confidence', 'Explanation'
                ]
            )
            wins_df['Entry'] = wins_df['Entry'].apply(lambda x: f"${x:,.2f}")
            wins_df['SL'] = wins_df['SL'].apply(lambda x: f"${x:,.2f}")
            wins_df['TP'] = wins_df['TP'].apply(lambda x: f"${x:,.2f}")
            wins_df['Exit'] = wins_df['Exit'].apply(lambda x: f"${x:,.2f}")
            wins_df['P&L'] = wins_df['P&L'].apply(lambda x: f"${x:,.2f}")
            wins_df['P&L %'] = wins_df['P&L %'].apply(lambda x: f"{x:.2f}%")
            wins_df['Confidence'] = wins_df['Confidence'].apply(lambda x: f"{(x or 0):.0f}/100")
            st.dataframe(wins_df, use_container_width=True)

        if loss_trades:
            st.error(f"🔴 LOSING TRADES ({len(loss_trades)})")
            losses_df = pd.DataFrame(
                loss_trades,
                columns=[
                    'Trade ID', 'TF', 'Entry Time', 'Entry', 'SL', 'TP', 'Exit Time', 'Exit',
                    'P&L', 'P&L %', 'Result', 'Direction', 'Confluence', 'RSI', 'HTF Bias',
                    'FVG Type', 'Close Reason', 'Confidence', 'Explanation'
                ]
            )
            losses_df['Entry'] = losses_df['Entry'].apply(lambda x: f"${x:,.2f}")
            losses_df['SL'] = losses_df['SL'].apply(lambda x: f"${x:,.2f}")
            losses_df['TP'] = losses_df['TP'].apply(lambda x: f"${x:,.2f}")
            losses_df['Exit'] = losses_df['Exit'].apply(lambda x: f"${x:,.2f}")
            losses_df['P&L'] = losses_df['P&L'].apply(lambda x: f"${x:,.2f}")
            losses_df['P&L %'] = losses_df['P&L %'].apply(lambda x: f"{x:.2f}%")
            losses_df['Confidence'] = losses_df['Confidence'].apply(lambda x: f"{(x or 0):.0f}/100")
            st.dataframe(losses_df, use_container_width=True)

    # Professional post-loss diagnosis and prevention controls.
    latest_loss_diag = st.session_state.trade_executor.trade_memory.get_latest_loss_diagnosis(timeframe=selected_timeframe)
    if latest_loss_diag:
        with st.expander("🧠 Latest Loss Diagnosis (Why it happened + How system adapts)", expanded=False):
            diag = latest_loss_diag
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Trade ID", str(diag['trade_id']))
            with c2:
                st.metric("Direction", diag['direction'])
            with c3:
                st.metric("P&L %", f"{diag['pnl_pct']:.2f}%")
            with c4:
                conf_text = "N/A" if diag['close_confidence'] is None else f"{diag['close_confidence']:.0f}/100"
                st.metric("Confidence", conf_text)

            st.write(f"**Close Reason:** {diag['close_reason']}")
            st.write(f"**Root Cause Analysis:** {diag['close_explanation']}")

            required_conf = max(55.0, float(diag['confluence_score']) + 15.0)
            st.info(
                f"Prevention Rule Active: Similar {diag['direction']} {diag['fvg_type']} setups on {diag['timeframe']} are blocked for 72h "
                f"unless confluence is >= {required_conf:.0f}."
            )
    
    # ========================================================================
    # AUTO-REFRESH MECHANISM
    # ========================================================================
    
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info(f"⏱️ **Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **Timeframe:** {selected_timeframe.upper()}")
    
    with col2:
        st.success("✅ Data loaded successfully")
    
    # Auto-refresh trigger
    if refresh_enabled:
        time.sleep(refresh_interval)
        st.rerun()

else:
    st.error("❌ **Failed to fetch data from Binance**")
    st.warning("""
    ### Troubleshooting Steps:
    1. **Check Internet Connection:** Ensure you're connected to the internet
    2. **VPN/Proxy:** If Binance is blocked in your region, try using a VPN
    3. **API Rate Limits:** Wait a few minutes and refresh the page
    4. **Firewall:** Check if your firewall is blocking api.binance.com
    5. **Service Status:** Visit [Binance Status](https://www.binance.com/en/support/announcement) to check if API is down
    
    **Error Details:** The app tried 3 times with exponential backoff but couldn't reach Binance API.
    """)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
### 📌 Disclaimer & Information
- **Status:** Educational Purpose Only
- **Risk Warning:** Not financial advice. Crypto trading carries high risk.
- **Features:** Smart Money Concepts (SMC), Machine Learning, Multi-Timeframe Analysis
- **Data Source:** Binance API (Real-time)
- **Always:** Do Your Own Research (DYOR) before trading!
""")

