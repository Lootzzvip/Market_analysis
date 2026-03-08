"""
Backtesting & Retesting Module
Complete backtesting framework with multiple strategies and performance analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')


class BacktestEngine:
    """Main backtesting engine for trading strategies"""
    
    def __init__(self, initial_capital=10000, db_path='backtest_results.db'):
        self.initial_capital = initial_capital
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize backtesting database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                win_rate REAL,
                profit_factor REAL,
                total_return REAL,
                total_return_pct REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                sortino_ratio REAL,
                avg_trade_pnl REAL,
                avg_win REAL,
                avg_loss REAL,
                consecutive_wins INTEGER,
                consecutive_losses INTEGER,
                best_trade REAL,
                worst_trade REAL,
                created_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                entry_time TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_time TEXT NOT NULL,
                exit_price REAL NOT NULL,
                position_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                pnl REAL NOT NULL,
                pnl_pct REAL NOT NULL,
                trade_duration TEXT,
                bars_held INTEGER,
                FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_equity_curve (
                run_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                equity REAL NOT NULL,
                cumulative_pnl REAL NOT NULL,
                drawdown REAL NOT NULL,
                FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id),
                PRIMARY KEY(run_id, timestamp)
            )
        """)
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def calculate_metrics(trades_data: List[Dict]) -> Dict:
        """Calculate trading performance metrics"""
        if not trades_data:
            return {}
        
        df_trades = pd.DataFrame(trades_data)
        
        total_trades = len(df_trades)
        winning_trades = len(df_trades[df_trades['pnl'] > 0])
        losing_trades = len(df_trades[df_trades['pnl'] < 0])
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Commission and slippage (2 basis points per trade)
        commission = df_trades['entry_value'].sum() * 0.0002
        
        total_pnl = df_trades['pnl'].sum() - commission
        total_return_pct = (total_pnl / 10000) * 100
        
        # Risk metrics
        winning_pnl = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        losing_pnl = abs(df_trades[df_trades['pnl'] <= 0]['pnl'].sum())
        
        profit_factor = (winning_pnl / losing_pnl) if losing_pnl > 0 else float('inf') if winning_pnl > 0 else 0
        
        avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0
        avg_win = winning_pnl / winning_trades if winning_trades > 0 else 0
        avg_loss = losing_pnl / losing_trades if losing_trades > 0 else 0
        
        # Consecutive wins/losses
        df_trades['win'] = df_trades['pnl'] > 0
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        
        current_streak_wins = 0
        current_streak_losses = 0
        
        for is_win in df_trades['win']:
            if is_win:
                current_streak_wins += 1
                current_streak_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_streak_wins)
            else:
                current_streak_losses += 1
                current_streak_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_streak_losses)
        
        best_trade = df_trades['pnl'].max()
        worst_trade = df_trades['pnl'].min()
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_return': total_pnl,
            'avg_trade_pnl': avg_trade_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'consecutive_wins': max_consecutive_wins,
            'consecutive_losses': max_consecutive_losses,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'commission': commission
        }
    
    @staticmethod
    def calculate_drawdown_and_sharpe(equity_curve: pd.Series, risk_free_rate=0.02) -> Tuple[float, float, float]:
        """
        Calculate maximum drawdown, Sharpe ratio, and Sortino ratio
        """
        if equity_curve.empty or len(equity_curve) < 2:
            return 0, 0, 0
        
        # Maximum drawdown
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # Returns
        returns = equity_curve.pct_change().dropna()
        
        if len(returns) == 0:
            return max_drawdown, 0, 0
        
        # Sharpe ratio (annualized, assuming 252 trading days)
        excess_returns = returns - (risk_free_rate / 252)
        sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252) if excess_returns.std() > 0 else 0
        
        # Sortino ratio (only penalizes downside volatility)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else returns.std()
        sortino_ratio = (excess_returns.mean() / downside_std) * np.sqrt(252) if downside_std > 0 else 0
        
        return max_drawdown, sharpe_ratio, sortino_ratio
    
    def run_backtest(self, df: pd.DataFrame, strategy_func, timeframe: str, 
                    strategy_name: str = "FVG_Strategy") -> Dict:
        """
        Run backtest on dataframe with given strategy
        
        Args:
            df: DataFrame with OHLCV and indicator data
            strategy_func: Function that returns signals {'type': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'tp': price}
            timeframe: Timeframe of the data (e.g., '1h', '4h')
            strategy_name: Name of the strategy
        
        Returns:
            Dictionary with backtest results
        """
        trades = []
        equity_curve = []
        current_equity = self.initial_capital
        
        # Track open positions
        open_position = None
        position_bars = 0
        
        # Generate signals for each candle
        for i in range(len(df)):
            current_price = df.iloc[i]['close']
            current_time = df.iloc[i]['timestamp']
            
            # Calculate equity at this point
            if open_position:
                # Mark to market
                if open_position['type'] == 'BUY':
                    position_pnl = (current_price - open_position['entry']) * open_position['quantity']
                else:
                    position_pnl = (open_position['entry'] - current_price) * open_position['quantity']
                
                current_equity = self.initial_capital + position_pnl + sum(t['pnl'] for t in trades)
            
            equity_curve.append({
                'timestamp': current_time,
                'equity': current_equity,
                'price': current_price
            })
            
            # Check if we should close position
            if open_position:
                position_bars += 1
                should_close = False
                exit_price = None
                close_reason = None
                
                # Check stop loss
                if open_position['type'] == 'BUY' and current_price <= open_position['stop_loss']:
                    should_close = True
                    exit_price = open_position['stop_loss']
                    close_reason = 'Stop Loss'
                
                # Check take profit
                if open_position['type'] == 'BUY' and current_price >= open_position['take_profit']:
                    should_close = True
                    exit_price = open_position['take_profit']
                    close_reason = 'Take Profit'
                
                # Sell stops
                if open_position['type'] == 'SELL' and current_price >= open_position['stop_loss']:
                    should_close = True
                    exit_price = open_position['stop_loss']
                    close_reason = 'Stop Loss'
                
                # Sell take profit
                if open_position['type'] == 'SELL' and current_price <= open_position['take_profit']:
                    should_close = True
                    exit_price = open_position['take_profit']
                    close_reason = 'Take Profit'
                
                # Time-based exit (max 50 bars)
                if position_bars > 50:
                    should_close = True
                    exit_price = current_price
                    close_reason = 'Timeout'
                
                if should_close and exit_price:
                    # Calculate P&L
                    if open_position['type'] == 'BUY':
                        pnl = (exit_price - open_position['entry']) * open_position['quantity']
                    else:
                        pnl = (open_position['entry'] - exit_price) * open_position['quantity']
                    
                    # Log trade
                    duration = (current_time - open_position['entry_time']).total_seconds() / 3600
                    trades.append({
                        'entry_time': open_position['entry_time'],
                        'exit_time': current_time,
                        'entry_price': open_position['entry'],
                        'exit_price': exit_price,
                        'position_type': open_position['type'],
                        'quantity': open_position['quantity'],
                        'pnl': pnl,
                        'pnl_pct': (pnl / (open_position['entry'] * open_position['quantity'])) * 100,
                        'duration_hours': duration,
                        'bars_held': position_bars,
                        'close_reason': close_reason,
                        'entry_value': open_position['entry'] * open_position['quantity']
                    })
                    
                    open_position = None
                    position_bars = 0
            
            # Generate signal for entry
            if not open_position:
                signal = strategy_func(df.iloc[:i+1])  # Pass data up to current point
                
                if signal.get('type') != 'NONE':
                    # Calculate position size (risk 2% per trade = 0.02 capital, or fixed quantity)
                    risk_amount = self.initial_capital * 0.02
                    entry_price = signal['entry']
                    stop_loss = signal['stop_loss']
                    risk_per_unit = abs(entry_price - stop_loss)
                    
                    if risk_per_unit > 0:
                        quantity = risk_amount / risk_per_unit
                    else:
                        quantity = 1
                    
                    open_position = {
                        'type': signal['type'],
                        'entry': entry_price,
                        'stop_loss': stop_loss,
                        'take_profit': signal['take_profit'],
                        'entry_time': current_time,
                        'quantity': quantity
                    }
        
        # Close any open position at end
        if open_position:
            final_price = df.iloc[-1]['close']
            if open_position['type'] == 'BUY':
                pnl = (final_price - open_position['entry']) * open_position['quantity']
            else:
                pnl = (open_position['entry'] - final_price) * open_position['quantity']
            
            trades.append({
                'entry_time': open_position['entry_time'],
                'exit_time': df.iloc[-1]['timestamp'],
                'entry_price': open_position['entry'],
                'exit_price': final_price,
                'position_type': open_position['type'],
                'quantity': open_position['quantity'],
                'pnl': pnl,
                'pnl_pct': (pnl / (open_position['entry'] * open_position['quantity'])) * 100,
                'entry_value': open_position['entry'] * open_position['quantity']
            })
        
        # Calculate metrics
        metrics = self.calculate_metrics(trades)
        
        # Calculate drawdown and Sharpe ratio
        df_equity = pd.DataFrame(equity_curve)
        if not df_equity.empty:
            max_dd, sharpe, sortino = self.calculate_drawdown_and_sharpe(df_equity['equity'])
            metrics['max_drawdown'] = max_dd
            metrics['sharpe_ratio'] = sharpe
            metrics['sortino_ratio'] = sortino
        
        # Final equity
        final_equity = self.initial_capital
        if trades:
            final_equity = self.initial_capital + sum(t['pnl'] for t in trades)
        
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        result = {
            'strategy_name': strategy_name,
            'timeframe': timeframe,
            'start_date': df.iloc[0]['timestamp'],
            'end_date': df.iloc[-1]['timestamp'],
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_trades': metrics.get('total_trades', 0),
            'winning_trades': metrics.get('winning_trades', 0),
            'losing_trades': metrics.get('losing_trades', 0),
            'win_rate': metrics.get('win_rate', 0),
            'profit_factor': metrics.get('profit_factor', 0),
            'total_return': final_equity - self.initial_capital,
            'total_return_pct': total_return_pct,
            'max_drawdown': metrics.get('max_drawdown', 0),
            'sharpe_ratio': metrics.get('sharpe_ratio', 0),
            'sortino_ratio': metrics.get('sortino_ratio', 0),
            'avg_trade_pnl': metrics.get('avg_trade_pnl', 0),
            'avg_win': metrics.get('avg_win', 0),
            'avg_loss': metrics.get('avg_loss', 0),
            'consecutive_wins': metrics.get('consecutive_wins', 0),
            'consecutive_losses': metrics.get('consecutive_losses', 0),
            'best_trade': metrics.get('best_trade', 0),
            'worst_trade': metrics.get('worst_trade', 0),
            'trades': trades,
            'equity_curve': equity_curve
        }
        
        return result
    
    def save_backtest_result(self, result: Dict, run_id=None):
        """Save backtest result to database"""
        conn = sqlite3.connect(self.db_path)
        
        cursor = conn.execute("""
            INSERT INTO backtest_runs (
                strategy_name, timeframe, start_date, end_date, total_trades,
                winning_trades, losing_trades, win_rate, profit_factor,
                total_return, total_return_pct, max_drawdown, sharpe_ratio,
                sortino_ratio, avg_trade_pnl, avg_win, avg_loss,
                consecutive_wins, consecutive_losses, best_trade, worst_trade, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result['strategy_name'],
            result['timeframe'],
            str(result['start_date']),
            str(result['end_date']),
            result['total_trades'],
            result['winning_trades'],
            result['losing_trades'],
            result['win_rate'],
            result['profit_factor'],
            result['total_return'],
            result['total_return_pct'],
            result['max_drawdown'],
            result['sharpe_ratio'],
            result['sortino_ratio'],
            result['avg_trade_pnl'],
            result['avg_win'],
            result['avg_loss'],
            result['consecutive_wins'],
            result['consecutive_losses'],
            result['best_trade'],
            result['worst_trade'],
            datetime.now().isoformat()
        ))
        
        run_id = cursor.lastrowid
        
        # Save individual trades
        for trade in result['trades']:
            conn.execute("""
                INSERT INTO backtest_trades (
                    run_id, entry_time, entry_price, exit_time, exit_price,
                    position_type, quantity, pnl, pnl_pct, bars_held
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                str(trade['entry_time']),
                trade['entry_price'],
                str(trade['exit_time']),
                trade['exit_price'],
                trade['position_type'],
                trade['quantity'],
                trade['pnl'],
                trade['pnl_pct'],
                trade.get('bars_held', 0)
            ))
        
        # Save equity curve
        for point in result['equity_curve']:
            conn.execute("""
                INSERT INTO backtest_equity_curve (run_id, timestamp, equity, cumulative_pnl, drawdown)
                VALUES (?, ?, ?, ?, ?)
            """, (
                run_id,
                str(point['timestamp']),
                point['equity'],
                point['equity'] - self.initial_capital,
                0  # Placeholder for now
            ))
        
        conn.commit()
        conn.close()
        
        return run_id
    
    def get_backtest_history(self, strategy_name=None, limit=10):
        """Get historical backtest results"""
        conn = sqlite3.connect(self.db_path)
        
        if strategy_name:
            df = pd.read_sql_query(
                "SELECT * FROM backtest_runs WHERE strategy_name = ? ORDER BY created_at DESC LIMIT ?",
                conn,
                params=(strategy_name, limit)
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?",
                conn,
                params=(limit,)
            )
        
        conn.close()
        return df
    
    def compare_backtests(self, run_ids: List[int]) -> pd.DataFrame:
        """Compare multiple backtest runs"""
        conn = sqlite3.connect(self.db_path)
        
        placeholders = ','.join('?' * len(run_ids))
        df = pd.read_sql_query(
            f"SELECT * FROM backtest_runs WHERE run_id IN ({placeholders})",
            conn,
            params=run_ids
        )
        
        conn.close()
        return df


class StrategyOptimizer:
    """Optimize trading strategy parameters"""
    
    @staticmethod
    def optimize_confluence_threshold(df, backtest_engine, timeframe, 
                                     thresholds=None, strategy_func=None):
        """Optimize confluence threshold parameter"""
        if thresholds is None:
            thresholds = list(range(40, 100, 5))
        
        results = []
        
        for threshold in thresholds:
            # Create strategy with this threshold
            def strategy(data):
                if len(data) < 5:
                    return {'type': 'NONE'}
                latest = data.iloc[-1]
                conf_score = latest.get('fvg_confluence_score', 0)
                if conf_score >= threshold and latest.get('fvg_type') != 'none':
                    return {
                        'type': 'BUY' if latest.get('fvg_type') == 'bullish' else 'SELL',
                        'entry': latest['close'],
                        'stop_loss': latest.get('support', latest['close'] * 0.99),
                        'take_profit': latest['close'] * 1.02
                    }
                return {'type': 'NONE'}
            
            result = backtest_engine.run_backtest(df, strategy, timeframe, f"Conv_Threshold_{threshold}")
            result['threshold'] = threshold
            results.append(result)
        
        # Find best result by Sharpe ratio
        best = max(results, key=lambda x: x['sharpe_ratio'] if x['sharpe_ratio'] > float('-inf') else -1)
        
        return {
            'all_results': results,
            'best_threshold': best['threshold'],
            'best_result': best
        }
    
    @staticmethod
    def optimize_rsi_levels(df, backtest_engine, timeframe, 
                           rsi_levels=None):
        """Optimize RSI overbought/oversold levels"""
        if rsi_levels is None:
            rsi_levels = [(70, 30), (75, 25), (80, 20), (85, 15)]
        
        results = []
        
        for overbought, oversold in rsi_levels:
            def strategy(data):
                if len(data) < 5:
                    return {'type': 'NONE'}
                latest = data.iloc[-1]
                rsi = latest.get('rsi', 50)
                
                if rsi > overbought:
                    return {
                        'type': 'SELL',
                        'entry': latest['close'],
                        'stop_loss': latest['close'] * 1.01,
                        'take_profit': latest['close'] * 0.98
                    }
                elif rsi < oversold:
                    return {
                        'type': 'BUY',
                        'entry': latest['close'],
                        'stop_loss': latest['close'] * 0.99,
                        'take_profit': latest['close'] * 1.02
                    }
                return {'type': 'NONE'}
            
            result = backtest_engine.run_backtest(df, strategy, timeframe, 
                                                 f"RSI_{overbought}_{oversold}")
            result['overbought'] = overbought
            result['oversold'] = oversold
            results.append(result)
        
        best = max(results, key=lambda x: x['total_return_pct'])
        
        return {
            'all_results': results,
            'best_levels': (best['overbought'], best['oversold']),
            'best_result': best
        }


class PerformanceAnalyzer:
    """Analyze trading performance across multiple backtests"""
    
    @staticmethod
    def generate_summary_report(backtest_results: List[Dict]) -> Dict:
        """Generate summary report for multiple backtest results"""
        if not backtest_results:
            return {}
        
        total_trades = sum(r['total_trades'] for r in backtest_results)
        total_returns = sum(r['total_return'] for r in backtest_results)
        avg_win_rate = np.mean([r['win_rate'] for r in backtest_results if r['total_trades'] > 0])
        avg_profit_factor = np.mean([r['profit_factor'] for r in backtest_results if r['total_trades'] > 0])
        avg_sharpe = np.mean([r['sharpe_ratio'] for r in backtest_results])
        
        return {
            'num_backtests': len(backtest_results),
            'total_trades': total_trades,
            'total_returns': total_returns,
            'avg_win_rate': avg_win_rate,
            'avg_profit_factor': avg_profit_factor,
            'avg_sharpe_ratio': avg_sharpe,
            'best_strategy': max(backtest_results, key=lambda x: x['total_return_pct'])['strategy_name'],
            'best_return_pct': max(backtest_results, key=lambda x: x['total_return_pct'])['total_return_pct']
        }
    
    @staticmethod
    def identify_strategy_improvements(before: Dict, after: Dict) -> Dict:
        """Identify improvements between two strategy versions"""
        improvements = {}
        
        metrics = ['total_trades', 'win_rate', 'profit_factor', 'sharpe_ratio', 'total_return_pct']
        
        for metric in metrics:
            before_val = before.get(metric, 0)
            after_val = after.get(metric, 0)
            change = after_val - before_val
            change_pct = (change / abs(before_val)) * 100 if before_val != 0 else 0
            
            improvements[metric] = {
                'before': before_val,
                'after': after_val,
                'change': change,
                'change_pct': change_pct,
                'improved': change > 0
            }
        
        return improvements
