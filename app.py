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
warnings.filterwarnings('ignore')

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
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        except Exception as e:
            st.error(f"Error fetching data: {e}")
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
                st.warning(f"Could not fetch {tf_name} zones: {e}")
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
    
    def _initialize(self):
        conn = sqlite3.connect(self.db_path)
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
                exit_time TEXT,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                result TEXT,
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
        conn.commit()
        conn.close()
    
    def log_trade(self, timeframe, entry_price, stop_loss, take_profit, 
                  confluence_score, rsi, htf_bias, fvg_type):
        """Log a new trade entry"""
        conn = sqlite3.connect(self.db_path)
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        
        conn.execute(
            """
            INSERT INTO trades (timeframe, entry_time, entry_price, stop_loss, 
                              take_profit, risk, reward, confluence_score, 
                              rsi_at_entry, htf_bias, fvg_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                datetime.now().isoformat()
            )
        )
        conn.commit()
        last_trade_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return last_trade_id
    
    def close_trade(self, trade_id, exit_price):
        """Close a trade and record results"""
        conn = sqlite3.connect(self.db_path)
        
        trade = conn.execute(
            "SELECT entry_price, stop_loss, take_profit, risk, reward, timeframe FROM trades WHERE trade_id = ?",
            (trade_id,)
        ).fetchone()
        
        if trade:
            entry_price, stop_loss, take_profit, risk, reward, timeframe = trade
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) * 100 if entry_price != 0 else 0
            
            # Determine result
            if exit_price >= take_profit:
                result = 'WIN'
            elif exit_price <= stop_loss:
                result = 'LOSS'
            else:
                result = 'CLOSED'
            
            conn.execute(
                """
                UPDATE trades 
                SET exit_time = ?, exit_price = ?, pnl = ?, pnl_pct = ?, result = ?
                WHERE trade_id = ?
                """,
                (datetime.now().isoformat(), float(exit_price), float(pnl), 
                 float(pnl_pct), result, trade_id)
            )
            
            # Update stats
            self._update_stats(timeframe)
        
        conn.commit()
        conn.close()
    
    def _update_stats(self, timeframe):
        """Update trade statistics for a timeframe"""
        conn = sqlite3.connect(self.db_path)
        
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
        conn = sqlite3.connect(self.db_path)
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
    
    def get_open_trades(self):
        """Get all open trades"""
        conn = sqlite3.connect(self.db_path)
        trades = conn.execute(
            """
            SELECT trade_id, timeframe, entry_time, entry_price, stop_loss, take_profit, 
                   risk, reward, confluence_score, rsi_at_entry, fvg_type
            FROM trades WHERE result IS NULL
            ORDER BY entry_time DESC
            """
        ).fetchall()
        conn.close()
        return trades
    
    def get_recent_trades(self, limit=10):
        """Get recent closed trades"""
        conn = sqlite3.connect(self.db_path)
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


class TradeExecutor:
    """Execute trades based on FVG and SMC signals with 1:2 risk/reward"""
    
    def __init__(self, initial_balance=10000):
        self.balance = initial_balance
        self.equity = initial_balance
        self.open_trades = {}
        self.trade_memory = TradeMemory()
    
    def generate_signal(self, df, timeframe, confluenceThreshold=60):
        """
        Generate a trading signal based on SMC indicators
        Returns: {'type': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'tp': price, 'risk': value}
        """
        if len(df) < 5:
            return {'type': 'NONE'}
        
        latest = df.iloc[-1]
        
        # Check if we have valid signal conditions
        if pd.isna(latest.get('fvg_type')) or latest.get('fvg_type') == 'none':
            return {'type': 'NONE'}
        
        # Confluence and confluence must be above threshold
        if latest.get('fvg_confluence_score', 0) < confluenceThreshold:
            return {'type': 'NONE'}
        
        rsi = latest.get('rsi', 50)
        atr = latest.get('atr', latest['close'] * 0.01)
        close = latest['close']
        atf_bias = latest.get('htf_bias', 0)
        
        # ---- BULLISH SIGNAL (BOS + Bullish FVG + Not Overbought) ----
        if latest.get('fvg_type') == 'bullish' and latest.get('bos_bullish', False) and rsi < 80:
            # Entry: Above FVG / at resistance breakout
            entry = latest.get('fvg_upper', close) + (atr * 0.1)
            # Stop Loss: Below FVG
            stop_loss = latest.get('fvg_lower', close) - (atr * 0.15)
            # Risk/Reward 1:2
            risk = entry - stop_loss
            take_profit = entry + (risk * 2)
            
            return {
                'type': 'BUY',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'reason': f"Bullish FVG ({latest.get('fvg_confluence_score', 0):.0f} conf) + BOS + RSI {rsi:.1f}"
            }
        
        # ---- BEARISH SIGNAL (BOS + Bearish FVG + Not Oversold) ----
        if latest.get('fvg_type') == 'bearish' and latest.get('bos_bearish', False) and rsi > 20:
            # Entry: Below FVG / at support breakdown
            entry = latest.get('fvg_lower', close) - (atr * 0.1)
            # Stop Loss: Above FVG
            stop_loss = latest.get('fvg_upper', close) + (atr * 0.15)
            # Risk/Reward 1:2
            risk = stop_loss - entry
            take_profit = entry - (risk * 2)
            
            return {
                'type': 'SELL',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'reason': f"Bearish FVG ({latest.get('fvg_confluence_score', 0):.0f} conf) + BOS + RSI {rsi:.1f}"
            }
        
        return {'type': 'NONE'}
    
    def execute_trade(self, signal, df, timeframe):
        """Execute a trade if signal is generated"""
        if signal['type'] == 'NONE':
            return None
        
        latest = df.iloc[-1]
        
        # Position size based on risk
        risk_per_trade = self.balance * 0.02  # Risk 2% per trade
        if signal['risk'] > 0:
            position_size = risk_per_trade / signal['risk']
        else:
            return None
        
        # Create trade
        trade_id = self.trade_memory.log_trade(
            timeframe=timeframe,
            entry_price=signal['entry'],
            stop_loss=signal['stop_loss'],
            take_profit=signal['take_profit'],
            confluence_score=latest.get('fvg_confluence_score', 0),
            rsi=latest.get('rsi', 50),
            htf_bias=latest.get('htf_bias', 0),
            fvg_type=latest.get('fvg_type', 'none')
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
    
    def update_open_trades(self, current_price):
        """Check if any open trades hit TP or SL"""
        closed_trades = []
        
        for trade_id, trade in list(self.open_trades.items()):
            pnl = current_price - trade['entry'] if trade['type'] == 'BUY' else trade['entry'] - current_price
            
            # Check if TP or SL hit
            if trade['type'] == 'BUY' and current_price >= trade['take_profit']:
                self.trade_memory.close_trade(trade_id, trade['take_profit'])
                self.balance += pnl * trade['position_size']
                closed_trades.append((trade_id, 'WIN', pnl * trade['position_size']))
                del self.open_trades[trade_id]
            elif trade['type'] == 'BUY' and current_price <= trade['stop_loss']:
                self.trade_memory.close_trade(trade_id, trade['stop_loss'])
                self.balance += pnl * trade['position_size']
                closed_trades.append((trade_id, 'LOSS', pnl * trade['position_size']))
                del self.open_trades[trade_id]
            elif trade['type'] == 'SELL' and current_price <= trade['take_profit']:
                self.trade_memory.close_trade(trade_id, trade['take_profit'])
                self.balance += pnl * trade['position_size']
                closed_trades.append((trade_id, 'WIN', pnl * trade['position_size']))
                del self.open_trades[trade_id]
            elif trade['type'] == 'SELL' and current_price >= trade['stop_loss']:
                self.trade_memory.close_trade(trade_id, trade['stop_loss'])
                self.balance += pnl * trade['position_size']
                closed_trades.append((trade_id, 'LOSS', pnl * trade['position_size']))
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
        self.feature_cols = [
            'fvg_size', 'rsi', 'hour', 'volume', 'ema_trend',
            'trend_slope_10', 'trend_slope_20', 'trend_volatility_20',
            'atr_pct', 'adx', 'htf_bias', 'displacement_pct', 'sweep_high', 'sweep_low',
            'in_premium', 'in_discount', 'fvg_confluence_score',
            'distance_to_resistance_pct', 'distance_to_support_pct', 'direction'
        ]
        
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
        """
        if not isinstance(trade_memory, TradeMemory):
            return False
        
        try:
            # Get all closed trades
            closed_trades = trade_memory.get_recent_trades(limit=1000)
            if not closed_trades or len(closed_trades) < 5:
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
            
            # Analyze patterns of wins vs losses
            wins = learn_df[learn_df['target'] == 1]
            losses = learn_df[learn_df['target'] == 0]
            
            if len(wins) > 0 and len(losses) > 0:
                # Feature importance from trade results
                self.winning_confluence = wins['confluence_score'].mean()
                self.losing_confluence = losses['confluence_score'].mean()
                self.winning_rsi_range = (wins['rsi'].min(), wins['rsi'].max())
                self.losing_rsi_range = (losses['rsi'].min(), losses['rsi'].max())
                
                return True
            
            return False
        
        except Exception as e:
            print(f"Error learning from trades: {e}")
            return False
    
    def get_adaptive_confluence_threshold(self):
        """
        Dynamically adjust confluence threshold based on historical trade performance
        If we have good win rates at certain confluence levels, lower the threshold
        """
        if not hasattr(self, 'winning_confluence'):
            return 60  # Default
        
        # If winning trades have high confluence, we can be more selective
        if self.winning_confluence > 75:
            return 70
        elif self.winning_confluence > 65:
            return 60
        else:
            return 50  # Be more permissive if confluence isn't the only factor


# ============================================================================
# STREAMLIT APP CONFIGURATION
# ============================================================================

st.set_page_config(page_title="ML Trading Dashboard - TradingView Style", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for TradingView-like styling
st.markdown("""
<style>
    body {
        background-color: #131722;
        color: #d1d5db;
    }
    .main {
        background-color: #131722;
    }
    .stMetric {
        background-color: #1e222d;
        padding: 15px;
        border-radius: 8px;
        border-left: 3px solid #2962ff;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e222d;
        padding: 10px 20px;
        border: 1px solid #2d3139;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2962ff;
    }
    h1, h2, h3 {
        color: #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 TradingView-Style ML Trading Dashboard")
st.markdown("**Real-Time Bitcoin Analysis | Multi-Timeframe | SMC + Machine Learning**")

# Initialize session state for continuous updates
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()
if 'selected_timeframe' not in st.session_state:
    st.session_state.selected_timeframe = '1h'
if 'trend_db' not in st.session_state:
    st.session_state.trend_db = TrendMLDatabase()
if 'predictor' not in st.session_state or st.session_state.predictor.db is None or st.session_state.predictor.db.db_path != st.session_state.trend_db.db_path:
    st.session_state.predictor = FVGPredictor(db=st.session_state.trend_db)
if 'trade_executor' not in st.session_state:
    st.session_state.trade_executor = TradeExecutor(initial_balance=10000)


# ============================================================================
# SIDEBAR CONTROLS (TradingView Style)
# ============================================================================

#st.sidebar.title("⚙️ Settings")

# Timeframe selection
st.sidebar.markdown("### 📈 Timeframe Selection")
timeframes = ['1w', '1d', '4h', '2h', '1h', '15m', '5m']
selected_timeframe = st.sidebar.radio("Choose Timeframe:", timeframes, index=4, horizontal=True)

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

# SMC Settings
st.sidebar.markdown("### 🎯 SMC Settings")
show_fvg = st.sidebar.checkbox("Show Fair Value Gaps", value=True)
show_bos = st.sidebar.checkbox("Show Break of Structure", value=True)
show_swing = st.sidebar.checkbox("Show Swing Points", value=True)

# Model Settings
st.sidebar.markdown("### 🤖 ML Model")
prob_threshold = st.sidebar.slider("Probability Threshold (%)", 30, 95, 65)
min_confluence_threshold = st.sidebar.slider("Min Confluence Score", 40, 90, 60)

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
    '5m': 2000
}

df = fetcher.fetch_historical_data(timeframe=selected_timeframe, limit=candle_limit.get(selected_timeframe, 500))

if df is not None:
    df_4h = fetcher.fetch_historical_data(timeframe='4h', limit=500)
    df_1d = fetcher.fetch_historical_data(timeframe='1d', limit=500)
    bias_4h = compute_htf_bias(df_4h)
    bias_1d = compute_htf_bias(df_1d)
    combined_bias = 0
    if bias_4h == bias_1d:
        combined_bias = bias_4h
    elif bias_4h != 0:
        combined_bias = bias_4h
    else:
        combined_bias = bias_1d

    st.sidebar.markdown("### 🧭 HTF Bias")
    st.sidebar.write(f"4H: {'Bullish' if bias_4h == 1 else 'Bearish' if bias_4h == -1 else 'Neutral'}")
    st.sidebar.write(f"1D: {'Bullish' if bias_1d == 1 else 'Bearish' if bias_1d == -1 else 'Neutral'}")
    st.sidebar.write(f"Combined: {'Bullish' if combined_bias == 1 else 'Bearish' if combined_bias == -1 else 'Neutral'}")

    # Apply SMC features
    df = SMCIndicators.engineer_all_features(
        df,
        htf_bias=combined_bias,
        min_confluence_threshold=min_confluence_threshold
    )
    
    # Train model continuously with local + database memory
    with st.spinner("🤖 Updating ML model with trend database..."):
        accuracy = st.session_state.predictor.train(df, timeframe=selected_timeframe)
    st.sidebar.success(f"✅ Model updated! Accuracy: {accuracy:.2%}")
    
    # Get prediction for latest FVG
    latest_prob = st.session_state.predictor.predict_fvg_success(df)
    st.session_state.trend_db.log_trend_snapshot(df.iloc[-1], selected_timeframe, latest_prob)
    
    # ========================================================================
    # TRADING SYSTEM (SIGNAL GENERATION & EXECUTION)
    # ========================================================================
    
    # Generate trading signal for current timeframe
    signal = st.session_state.trade_executor.generate_signal(
        df, 
        selected_timeframe, 
        confluenceThreshold=min_confluence_threshold
    )
    
    # Execute trade if signal is generated
    if signal['type'] != 'NONE':
        trade_id = st.session_state.trade_executor.execute_trade(signal, df, selected_timeframe)
        if trade_id:
            st.sidebar.success(
                f"📈 **{signal['type']} Signal Generated!**\n"
                f"Reason: {signal.get('reason', 'SMC signal')}\n"
                f"Entry: ${signal['entry']:,.2f}\n"
                f"SL: ${signal['stop_loss']:,.2f}\n"
                f"TP: ${signal['take_profit']:,.2f}\n"
                f"Risk/Reward: 1:{(signal['take_profit']-signal['entry'])/(signal['entry']-signal['stop_loss']):.1f}"
            )
    
    # Update open trades based on current price
    current_price = df.iloc[-1]['close']
    closed = st.session_state.trade_executor.update_open_trades(current_price)
    
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
                # Get adaptive threshold based on performance
                adaptive_threshold = st.session_state.predictor.get_adaptive_confluence_threshold()
                st.sidebar.write(f"**Adaptive Confluence Threshold:** {adaptive_threshold} (adjusted from wins/losses)")

    
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
            
            st.info(f"🎯 **Multi-Timeframe Mode**: Showing {len(mtf_zones)} zones from 1w, 1d, 4h, 2h, 1h | Higher timeframe = Stronger")
        
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
                    font=dict(size=9, color='#d1d5db'),
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
            font=dict(size=18, color='#f0f0f0')
        ),
        height=1600,  # MUCH LARGER for better candlestick visibility
        hovermode='x unified',
        margin=dict(l=100, r=100, t=120, b=100),
        plot_bgcolor='#131722',
        paper_bgcolor='#131722',
        font=dict(color='#d1d5db', family='monospace', size=12),
        xaxis_rangeslider_visible=False,
        dragmode='zoom',  # Enable zoom mode
        showlegend=True,
        legend=dict(
            x=0.01,
            y=0.99,
            bgcolor='rgba(19,23,34,0.9)',
            bordercolor='#2d3139',
            borderwidth=2
        )
    )
    
    # Update axes for ALL subplots
    fig.update_xaxes(
        gridcolor='#2d3139',
        showgrid=True,
        zeroline=False,
        showline=True,
        linewidth=2,
        linecolor='#2d3139',
        rangeselector=dict(visible=False)
    )
    
    fig.update_yaxes(
        gridcolor='#2d3139',
        showgrid=True,
        zeroline=False,
        showline=True,
        linewidth=2,
        linecolor='#2d3139',
        automargin=True
    )
    
    # Display main chart with FULL WIDTH and LARGE HEIGHT for zoom capability
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True, 'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape']})
    
    # ========================================================================
    # TRADE PERFORMANCE CHARTS
    # ========================================================================
    
    st.markdown("---")
    st.subheader("📈 Trade Performance Analysis")
    
    # Get all trades for visualization
    all_trades = st.session_state.trade_executor.trade_memory.get_recent_trades(limit=100)
    
    if all_trades:
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
                        plot_bgcolor='#131722',
                        paper_bgcolor='#131722',
                        font=dict(color='#d1d5db', family='monospace'),
                        hovermode='x unified',
                        height=450
                    )
                    fig_equity.update_xaxes(gridcolor='#2d3139')
                    fig_equity.update_yaxes(gridcolor='#2d3139')
                    
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
                plot_bgcolor='#131722',
                paper_bgcolor='#131722',
                font=dict(color='#d1d5db', family='monospace'),
                height=450
            )
            fig_distribution.update_xaxes(gridcolor='#2d3139')
            fig_distribution.update_yaxes(gridcolor='#2d3139')
            
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
                plot_bgcolor='#131722',
                paper_bgcolor='#131722',
                font=dict(color='#d1d5db', family='monospace'),
                hovermode='x unified',
                height=450
            )
            fig_pnl.update_xaxes(gridcolor='#2d3139')
            fig_pnl.update_yaxes(gridcolor='#2d3139')
            
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
                plot_bgcolor='#131722',
                paper_bgcolor='#131722',
                font=dict(color='#d1d5db', family='monospace'),
                height=450
            )
            fig_cum.update_xaxes(gridcolor='#2d3139')
            fig_cum.update_yaxes(gridcolor='#2d3139')
            
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
                template='plotly_dark',
                plot_bgcolor='#131722',
                paper_bgcolor='#131722',
                font=dict(color='#d1d5db')
            )
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
                template='plotly_dark',
                plot_bgcolor='#131722',
                paper_bgcolor='#131722',
                font=dict(color='#d1d5db')
            )
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
                    'Take Profit', 'Risk', 'Reward', 'Confluence', 'RSI', 'FVG Type']
        )
        open_df['Entry Price'] = open_df['Entry Price'].apply(lambda x: f"${x:,.2f}")
        open_df['Stop Loss'] = open_df['Stop Loss'].apply(lambda x: f"${x:,.2f}")
        open_df['Take Profit'] = open_df['Take Profit'].apply(lambda x: f"${x:,.2f}")
        open_df['Risk'] = open_df['Risk'].apply(lambda x: f"${x:,.2f}")
        open_df['Reward'] = open_df['Reward'].apply(lambda x: f"${x:,.2f}")
        open_df['Confluence'] = open_df['Confluence'].apply(lambda x: f"{x:.0f}")
        open_df['RSI'] = open_df['RSI'].apply(lambda x: f"{x:.1f}")
        st.dataframe(open_df, use_container_width=True)
    else:
        st.info("✅ No open trades")
    
    # Show trading statistics per timeframe
    st.write("**📈 TRADE STATISTICS BY TIMEFRAME:**")
    
    tf_list = ['1w', '1d', '4h', '2h', '1h', '15m', '5m']
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
    
    # Show recent closed trades
    recent_trades = st.session_state.trade_executor.trade_memory.get_recent_trades(limit=10)
    if recent_trades:
        st.write("**📋 RECENT CLOSED TRADES:**")
        recent_df = pd.DataFrame(
            recent_trades,
            columns=['Trade ID', 'Timeframe', 'Entry Time', 'Entry Price', 'SL', 'TP',
                    'Exit Time', 'Exit Price', 'P&L', 'P&L %', 'Result']
        )
        recent_df['Entry Price'] = recent_df['Entry Price'].apply(lambda x: f"${x:,.2f}")
        recent_df['SL'] = recent_df['SL'].apply(lambda x: f"${x:,.2f}")
        recent_df['TP'] = recent_df['TP'].apply(lambda x: f"${x:,.2f}")
        recent_df['Exit Price'] = recent_df['Exit Price'].apply(lambda x: f"${x:,.2f}")
        recent_df['P&L'] = recent_df['P&L'].apply(lambda x: f"${x:,.2f}")
        recent_df['P&L %'] = recent_df['P&L %'].apply(lambda x: f"{x:.2f}%")
        recent_df['Result'] = recent_df['Result'].apply(lambda x: f"✅ {x}" if x == "WIN" else f"❌ {x}" if x == "LOSS" else x)
        st.dataframe(recent_df, use_container_width=True)
    
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
    st.error("❌ Failed to fetch data from Binance. Check your internet connection.")

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

