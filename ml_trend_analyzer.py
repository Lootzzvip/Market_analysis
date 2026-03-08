"""
ML Trend Analyzer Module
Advanced machine learning for trend understanding, classification, and prediction
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import sqlite3
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class MLTrendAnalyzer:
    """Machine Learning based trend analysis and classification"""
    
    def __init__(self, db_path='ml_trends.db'):
        self.db_path = db_path
        self.scaler = StandardScaler()
        self.trend_model = None
        self.momentum_model = None
        self.reversal_model = None
        self._initialize_db()
        self._load_or_create_models()
    
    def _initialize_db(self):
        """Initialize machine learning database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trend_predictions (
                timestamp TEXT PRIMARY KEY,
                timeframe TEXT NOT NULL,
                trend_type TEXT NOT NULL,
                trend_strength REAL,
                momentum REAL,
                reversal_probability REAL,
                confidence REAL,
                actual_direction INTEGER,
                prediction_correct INTEGER,
                created_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_performance (
                timeframe TEXT PRIMARY KEY,
                model_type TEXT,
                accuracy REAL,
                precision REAL,
                recall REAL,
                f1 REAL,
                training_samples INTEGER,
                last_updated TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trend_regime_history (
                timestamp TEXT PRIMARY KEY,
                timeframe TEXT NOT NULL,
                regime_type TEXT,
                regime_confidence REAL,
                support_level REAL,
                resistance_level REAL,
                created_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _load_or_create_models(self):
        """Initialize ML models"""
        # Trend classification model: Strong Bull, Bull, Sideways, Bear, Strong Bear
        self.trend_model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        # Momentum model: Increasing, Stable, Decreasing
        self.momentum_model = GradientBoostingClassifier(n_estimators=50, max_depth=5, random_state=42)
        # Reversal model: High probability, Medium, Low
        self.reversal_model = MLPClassifier(hidden_layer_sizes=(50, 25), max_iter=1000, random_state=42)
    
    @staticmethod
    def prepare_trend_features(df):
        """Extract features for trend machine learning"""
        features = pd.DataFrame(index=df.index)
        
        # Price action features
        features['close_sma20'] = df['close'] / df['close'].rolling(20).mean()
        features['close_sma50'] = df['close'] / df['close'].rolling(50).mean()
        features['ema_fast_slow_ratio'] = df['close'].ewm(span=20).mean() / df['close'].ewm(span=50).mean()
        
        # Momentum features
        features['rsi'] = df['rsi'] / 50  # Normalize
        features['momentum_10'] = df['close'].pct_change(10)
        features['momentum_20'] = df['close'].pct_change(20)
        features['momentum_50'] = df['close'].pct_change(50)
        
        # Volatility features
        features['volatility_20'] = df['close'].pct_change().rolling(20).std()
        features['volatility_50'] = df['close'].pct_change().rolling(50).std()
        features['atr_ratio'] = df['atr'] / df['close'] if 'atr' in df.columns else 0.01
        
        # Trend strength features
        features['trend_strength_short'] = df['close'].ewm(span=5).mean() - df['close'].ewm(span=20).mean()
        features['trend_strength_medium'] = df['close'].ewm(span=20).mean() - df['close'].ewm(span=50).mean()
        features['trend_strength_long'] = df['close'].ewm(span=50).mean() - df['close'].ewm(span=200).mean()
        
        # Reversal signals
        features['rsi_extremes'] = ((df['rsi'] < 30) | (df['rsi'] > 70)).astype(int)
        features['price_extreme'] = ((df['close'] > df['high'].rolling(50).mean() + 2*df['close'].pct_change().rolling(50).std()) | 
                                      (df['close'] < df['low'].rolling(50).mean() - 2*df['close'].pct_change().rolling(50).std())).astype(int)
        
        # Volume features
        if 'volume' in df.columns:
            features['volume_ma_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        else:
            features['volume_ma_ratio'] = 1.0
        
        # Range features
        features['high_low_ratio'] = (df['high'] - df['low']) / df['close']
        features['body_size_ratio'] = (df['close'] - df['open']).abs() / df['close']
        
        # Trend regime
        features['market_trend'] = df['market_trend'] if 'market_trend' in df.columns else 1
        
        # Fill NaN values
        features = features.fillna(0)
        
        return features
    
    @staticmethod
    def create_trend_labels(df, lookahead=5):
        """Create labels for trend classification (5 classes)"""
        # Calculate future return
        future_return = df['close'].shift(-lookahead) / df['close'] - 1
        
        # Create 5 trend classes
        labels = pd.Series(2, index=df.index)  # Default: sideways
        strong_bull_threshold = 0.02
        bull_threshold = 0.01
        bear_threshold = -0.01
        strong_bear_threshold = -0.02
        
        labels[future_return > strong_bull_threshold] = 4  # Strong Bull
        labels[(future_return > bull_threshold) & (future_return <= strong_bull_threshold)] = 3  # Bull
        labels[(future_return > bear_threshold) & (future_return <= bull_threshold)] = 2  # Sideways
        labels[(future_return > strong_bear_threshold) & (future_return <= bear_threshold)] = 1  # Bear
        labels[future_return <= strong_bear_threshold] = 0  # Strong Bear
        
        return labels
    
    def train_trend_models(self, df):
        """Train ML models on historical data"""
        if len(df) < 100:
            return False
        
        # Prepare features and labels
        features = self.prepare_trend_features(df)
        labels = self.create_trend_labels(df, lookahead=5)
        
        # Remove rows with NaN labels
        valid_idx = ~labels.isna()
        features = features[valid_idx]
        labels = labels[valid_idx]
        
        if len(features) < 50:
            return False
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train models
        try:
            self.trend_model.fit(X_train_scaled, y_train)
            y_pred = self.trend_model.predict(X_test_scaled)
            
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            
            return {
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'samples': len(X_train)
            }
        except Exception as e:
            print(f"Error training trend models: {e}")
            return False
    
    def predict_trend(self, df):
        """Predict trend classification and strength"""
        if self.trend_model is None or len(df) < 20:
            return None
        
        try:
            features = self.prepare_trend_features(df)
            latest_features = features.iloc[-1].values.reshape(1, -1)
            latest_features_scaled = self.scaler.transform(latest_features)
            
            # Predict trend
            trend_pred = self.trend_model.predict(latest_features_scaled)[0]
            trend_proba = self.trend_model.predict_proba(latest_features_scaled)[0]
            
            # Map predictions to trend names
            trend_names = {0: 'Strong Bear', 1: 'Bear', 2: 'Sideways', 3: 'Bull', 4: 'Strong Bull'}
            trend_trend = trend_names[trend_pred]
            confidence = float(np.max(trend_proba))
            
            # Calculate trend strength
            latest_row = df.iloc[-1]
            ema_fast_slow = latest_row['ema_fast'] - latest_row['ema_slow'] if 'ema_fast' in latest_row else 0
            trend_strength = float(ema_fast_slow / latest_row['close'])
            
            return {
                'trend': trend_trend,
                'trend_class': trend_pred,
                'confidence': confidence,
                'strength': trend_strength,
                'probabilities': dict(zip(trend_names.values(), trend_proba))
            }
        except Exception as e:
            print(f"Error predicting trend: {e}")
            return None
    
    @staticmethod
    def identify_trend_regime(df, period=20):
        """Identify current trend regime"""
        if len(df) < period:
            return None
        
        recent = df.tail(period)
        close_prices = recent['close'].values
        
        # Calculate trend using linear regression
        x = np.arange(len(close_prices))
        coeffs = np.polyfit(x, close_prices, 1)
        slope = coeffs[0]
        momentum = (close_prices[-1] - close_prices[0]) / close_prices[0]
        
        # Determine regime
        if slope > 0 and momentum > 0:
            regime = 'Uptrend'
            confidence = min(1.0, abs(slope / close_prices.mean()) * 100)
        elif slope < 0 and momentum < 0:
            regime = 'Downtrend'
            confidence = min(1.0, abs(slope / close_prices.mean()) * 100)
        else:
            regime = 'Sideways'
            confidence = 0.5 + abs(momentum) * 5
        
        # Support and resistance
        support = recent['low'].min()
        resistance = recent['high'].max()
        
        return {
            'regime': regime,
            'confidence': confidence,
            'support': float(support),
            'resistance': float(resistance),
            'momentum': float(momentum)
        }
    
    def detect_reversals(self, df):
        """Detect potential trend reversals"""
        if len(df) < 20:
            return None
        
        latest = df.iloc[-1]
        rsi = latest.get('rsi', 50)
        close = latest['close']
        high_50 = df.tail(50)['high'].max()
        low_50 = df.tail(50)['low'].min()
        
        reversals = []
        
        # Overbought reversal
        if rsi > 75:
            reversal_prob = min(1.0, (rsi - 70) / 30)
            reversals.append({
                'type': 'Overbought',
                'probability': reversal_prob,
                'rsi': float(rsi),
                'signal': 'Potential bearish reversal'
            })
        
        # Oversold reversal
        if rsi < 25:
            reversal_prob = min(1.0, (30 - rsi) / 30)
            reversals.append({
                'type': 'Oversold',
                'probability': reversal_prob,
                'rsi': float(rsi),
                'signal': 'Potential bullish reversal'
            })
        
        # Price extreme reversal
        if close >= high_50 * 0.99:
            reversals.append({
                'type': 'Price Extreme High',
                'probability': 0.6,
                'signal': 'Price at recent highs - watch for reversal'
            })
        
        if close <= low_50 * 1.01:
            reversals.append({
                'type': 'Price Extreme Low',
                'probability': 0.6,
                'signal': 'Price at recent lows - watch for reversal'
            })
        
        return reversals if reversals else None
    
    def log_prediction(self, timestamp, timeframe, trend_pred, confidence):
        """Log trend prediction to database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO trend_predictions (
                timestamp, timeframe, trend_type, trend_strength, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            timeframe,
            trend_pred.get('trend', 'Unknown'),
            trend_pred.get('strength', 0),
            confidence,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
    
    def get_trend_history(self, timeframe, limit=100):
        """Get recent trend predictions"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            "SELECT * FROM trend_predictions WHERE timeframe = ? ORDER BY timestamp DESC LIMIT ?",
            conn,
            params=(timeframe, limit)
        )
        conn.close()
        return df


class MomentumAnalyzer:
    """Analyze momentum and acceleration in trends"""
    
    @staticmethod
    def calculate_momentum_oscillator(df, fast=12, slow=26):
        """Calculate momentum oscillator"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        momentum_osc = ema_fast - ema_slow
        signal = momentum_osc.ewm(span=9, adjust=False).mean()
        
        df['momentum_oscillator'] = momentum_osc
        df['momentum_signal'] = signal
        df['momentum_histogram'] = momentum_osc - signal
        
        return df
    
    @staticmethod
    def calculate_rate_of_change(df, period=12):
        """Calculate Rate of Change (ROC)"""
        df['roc'] = ((df['close'] - df['close'].shift(period)) / df['close'].shift(period)) * 100
        df['roc_ma'] = df['roc'].rolling(window=5).mean()
        return df
    
    @staticmethod
    def detect_momentum_divergence(df, period=14):
        """Detect momentum divergence - price makes new high but momentum doesn't"""
        df['momentum_divergence'] = False
        df['divergence_type'] = 'none'
        
        recent_prices = df['close'].tail(period)
        recent_rsi = df['rsi'].tail(period) if 'rsi' in df.columns else None
        
        if recent_rsi is None:
            return df
        
        current_price = recent_prices.iloc[-1]
        current_rsi = recent_rsi.iloc[-1]
        
        price_high = recent_prices.max()
        rsi_high = recent_rsi.max()
        
        # Bullish divergence: price lower but RSI higher
        if current_price < price_high and current_rsi > rsi_high:
            df.loc[df.index[-1], 'momentum_divergence'] = True
            df.loc[df.index[-1], 'divergence_type'] = 'bullish'
        
        # Bearish divergence: price higher but RSI lower
        if current_price > price_high and current_rsi < rsi_high:
            df.loc[df.index[-1], 'momentum_divergence'] = True
            df.loc[df.index[-1], 'divergence_type'] = 'bearish'
        
        return df


class TrendConfluenceScorer:
    """Score confidence levels based on multiple trend indicators"""
    
    @staticmethod
    def calculate_confluence_score(df):
        """Calculate multi-indicator confluence score (0-100)"""
        if df.empty:
            return 0
        
        latest = df.iloc[-1]
        score = 0
        indicators_count = 0
        
        # EMA convergence (0-15 points)
        if 'ema_fast' in latest and 'ema_slow' in latest:
            ema_diff = abs(latest['ema_fast'] - latest['ema_slow']) / latest['close']
            if ema_diff < 0.001:  # Very close
                score += 15
            elif ema_diff < 0.005:
                score += 10
            elif ema_diff < 0.01:
                score += 5
            indicators_count += 1
        
        # RSI confluence (0-15 points)
        if 'rsi' in latest:
            if 25 < latest['rsi'] < 75:
                score += 8
            if (latest['rsi'] > 50 and latest.get('market_trend', 0) == 1) or \
               (latest['rsi'] < 50 and latest.get('market_trend', 0) == -1):
                score += 7
            indicators_count += 1
        
        # ADX trend strength (0-15 points)
        if 'adx' in latest:
            if latest['adx'] > 25:
                score += 15
            elif latest['adx'] > 20:
                score += 10
            elif latest['adx'] > 15:
                score += 5
            indicators_count += 1
        
        # ATR volatility (0-10 points)
        if 'atr_pct' in latest:
            if 0.3 < latest['atr_pct'] < 2.0:
                score += 10
            elif latest['atr_pct'] > 0.1:
                score += 5
            indicators_count += 1
        
        # Volume (0-20 points)
        if 'volume_ma_ratio' in latest:
            vol_ratio = latest['volume_ma_ratio']
            if vol_ratio > 1.3:
                score += 20
            elif vol_ratio > 1.1:
                score += 15
            elif vol_ratio > 1.0:
                score += 10
            indicators_count += 1
        
        # Structure (BOS/ChoCh/OB) (0-10 points)
        bos_count = int(latest.get('bos_bullish', False)) + int(latest.get('bos_bearish', False))
        choch_count = int(latest.get('choch_bullish', False)) + int(latest.get('choch_bearish', False))
        ob_count = int(latest.get('ob_bullish', False)) + int(latest.get('ob_bearish', False))
        
        if bos_count > 0 or choch_count > 0 or ob_count > 0:
            score += 10
        indicators_count += 1
        
        # Normalize if no indicator is available
        if indicators_count == 0:
            return 50
        
        return min(100, int(score))
