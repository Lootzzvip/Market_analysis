"""
Integration Example: Adding ML Trends to Streamlit UI
Shows how to display ML predictions and backtest results in the existing app.py
"""

# Add this code to your app.py to display ML trends in the Streamlit UI

import streamlit as st
from ml_trend_analyzer import MLTrendAnalyzer, TrendConfluenceScorer, MomentumAnalyzer
from backtest_engine import BacktestEngine, PerformanceAnalyzer
import plotly.graph_objects as go
from datetime import datetime

# ============================================================================
# SECTION 1: Add to Streamlit Sidebar (Add ML Trend Tab)
# ============================================================================

def show_ml_trend_analysis_ui(fetcher, df, selected_timeframe):
    """
    Display ML Trend Analysis in Streamlit
    Add this function to your app.py and call it in the main UI
    
    Usage in main app:
    if tab == "🤖 ML Trends":
        show_ml_trend_analysis_ui(fetcher, df, selected_timeframe)
    """
    
    st.subheader("🤖 ML Trend Analysis")
    
    # Initialize analyzer
    analyzer = MLTrendAnalyzer()
    
    # Column 1: Trend Prediction
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("### Current Trend")
        prediction = analyzer.predict_trend(df)
        
        if prediction:
            trend = prediction['trend']
            confidence = prediction['confidence']
            
            # Color code by trend
            if 'Bull' in trend:
                color = '🟢'
            elif 'Bear' in trend:
                color = '🔴'
            else:
                color = '⚫'
            
            st.metric(
                f"{color} Trend",
                trend,
                f"{confidence:.1%} confidence"
            )
            
            st.write(f"Strength: {prediction['strength']:.4f}")
            
            # Probability bars
            st.write("**Probability Distribution:**")
            for trend_name, prob in prediction['probabilities'].items():
                st.progress(prob, text=f"{trend_name}: {prob:.1%}")
    
    with col2:
        st.write("### Market Regime")
        regime = analyzer.identify_trend_regime(df, period=20)
        
        if regime:
            regime_color = {
                'Uptrend': '🟢',
                'Downtrend': '🔴',
                'Sideways': '⚫'
            }
            
            st.metric(
                f"{regime_color.get(regime['regime'], '⚫')} Regime",
                regime['regime'],
                f"{regime['confidence']:.1%}"
            )
            
            st.write(f"**Support:** ${regime['support']:.2f}")
            st.write(f"**Resistance:** ${regime['resistance']:.2f}")
    
    with col3:
        st.write("### Confluence Score")
        score = TrendConfluenceScorer.calculate_confluence_score(df)
        
        # Display as gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=score,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Confidence"},
            delta={'reference': 70},
            gauge={'axis': {'range': [0, 100]},
                   'bar': {'color': "darkblue"},
                   'steps': [
                       {'range': [0, 40], 'color': "lightgray"},
                       {'range': [40, 70], 'color': "gray"},
                       {'range': [70, 100], 'color': "green"}
                   ],
                   'threshold': {
                       'line': {'color': "red", 'width': 4},
                       'thickness': 0.75,
                       'value': 85
                   }}
        ))
        fig.update_layout(height=250)
        st.plotly_chart(fig, use_container_width=True)
    
    # Reversal Detection
    st.write("### 🔄 Reversal Detection")
    reversals = analyzer.detect_reversals(df)
    
    if reversals:
        for reversal in reversals:
            prob = reversal.get('probability', 0)
            signal = reversal.get('signal', '')
            
            col = "🟢" if prob > 0.7 else "🟡" if prob > 0.4 else "🔴"
            with st.expander(f"{col} {reversal['type']} - {prob:.0%} probability"):
                st.write(signal)
                st.write(f"**Probability:** {prob:.1%}")
    else:
        st.info("No reversals detected at this time")
    
    # Momentum Analysis
    st.write("### 📈 Momentum Analysis")
    
    df_momentum = MomentumAnalyzer.calculate_momentum_oscillator(df)
    df_momentum = MomentumAnalyzer.detect_momentum_divergence(df_momentum)
    
    latest = df_momentum.iloc[-1]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Momentum Oscillator",
            f"{latest['momentum_oscillator']:.4f}",
            "Signal" if latest['momentum_oscillator'] > latest['momentum_signal'] else "Against"
        )
    
    with col2:
        st.metric(
            "Rate of Change",
            f"{latest['roc']:.2f}%"
        )
    
    with col3:
        div_text = latest['divergence_type'].upper() if latest.get('momentum_divergence') else "NONE"
        st.metric(
            "Divergence",
            div_text
        )
    
    # Plot momentum
    momentum_fig = go.Figure()
    
    momentum_fig.add_trace(go.Scatter(
        x=df_momentum['timestamp'],
        y=df_momentum['momentum_oscillator'],
        name='Momentum Oscillator',
        yaxis='y2'
    ))
    
    momentum_fig.add_trace(go.Scatter(
        x=df_momentum['timestamp'],
        y=df_momentum['momentum_signal'],
        name='Signal',
        yaxis='y2'
    ))
    
    momentum_fig.update_layout(
        title="Momentum Oscillator",
        hovermode='x unified',
        yaxis2=dict(title="Momentum", side='right')
    )
    
    st.plotly_chart(momentum_fig, use_container_width=True)
    
    # Model Performance
    st.write("### 🎯 ML Model Performance")
    
    with st.spinner("Training models..."):
        training_results = analyzer.train_trend_models(df)
    
    if training_results:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Accuracy", f"{training_results['accuracy']:.1%}")
        with col2:
            st.metric("Precision", f"{training_results['precision']:.1%}")
        with col3:
            st.metric("Recall", f"{training_results['recall']:.1%}")
        with col4:
            st.metric("F1 Score", f"{training_results['f1']:.1%}")


# ============================================================================
# SECTION 2: Add Backtesting Tab
# ============================================================================

def show_backtesting_ui(df, selected_timeframe):
    """
    Display Backtesting Interface
    Add this to app.py as another tab option
    """
    
    st.subheader("📊 Strategy Backtesting")
    
    backtest_engine = BacktestEngine()
    
    # Sidebar options
    col1, col2 = st.columns(2)
    
    with col1:
        strategy_type = st.selectbox(
            "Strategy Type",
            ["FVG Strategy", "Custom RSI", "Momentum Based"]
        )
    
    with col2:
        initial_capital = st.number_input(
            "Initial Capital",
            value=10000,
            min_value=1000,
            step=1000
        )
    
    # Strategy selection
    if strategy_type == "FVG Strategy":
        def strategy(data):
            if len(data) < 5:
                return {'type': 'NONE'}
            
            latest = data.iloc[-1]
            
            if not latest.get('fvg_valid', False):
                return {'type': 'NONE'}
            
            conf_score = latest.get('fvg_confluence_score', 0)
            rsi = latest.get('rsi', 50)
            atr = latest.get('atr', latest['close'] * 0.01)
            
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
    
    elif strategy_type == "Custom RSI":
        def strategy(data):
            if len(data) < 5:
                return {'type': 'NONE'}
            
            latest = data.iloc[-1]
            rsi = latest.get('rsi', 50)
            
            if rsi < 30:
                return {
                    'type': 'BUY',
                    'entry': latest['close'],
                    'stop_loss': latest['close'] * 0.99,
                    'take_profit': latest['close'] * 1.02
                }
            elif rsi > 70:
                return {
                    'type': 'SELL',
                    'entry': latest['close'],
                    'stop_loss': latest['close'] * 1.01,
                    'take_profit': latest['close'] * 0.98
                }
            
            return {'type': 'NONE'}
    
    # Run backtest button
    if st.button("▶️ Run Backtest", key="run_backtest"):
        with st.spinner("Running backtest..."):
            backtest_engine.initial_capital = initial_capital
            result = backtest_engine.run_backtest(
                df, strategy, selected_timeframe, strategy_type
            )
        
        # Display results
        st.success("✅ Backtest Complete!")
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", result['total_trades'])
        with col2:
            st.metric("Win Rate", f"{result['win_rate']:.1f}%")
        with col3:
            st.metric("Profit Factor", f"{result['profit_factor']:.2f}")
        with col4:
            st.metric("Sharpe Ratio", f"{result['sharpe_ratio']:.2f}")
        
        # Returns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Initial Capital", f"${result['initial_capital']:,.0f}")
        with col2:
            st.metric("Final Equity", f"${result['final_equity']:,.0f}")
        with col3:
            return_color = "🟢" if result['total_return'] > 0 else "🔴"
            st.metric(
                f"{return_color} Total Return",
                f"${result['total_return']:,.0f}",
                f"{result['total_return_pct']:+.2f}%"
            )
        
        # Risk metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Max Drawdown", f"{result['max_drawdown']:.2%}")
        with col2:
            st.metric("Avg Win", f"${result['avg_win']:,.0f}")
        with col3:
            st.metric("Avg Loss", f"${result['avg_loss']:,.0f}")
        
        # Equity Curve
        st.write("### Equity Curve")
        
        equity_df = df.copy()
        equity_df['equity'] = [point['equity'] for point in result['equity_curve']]
        
        equity_fig = go.Figure()
        
        equity_fig.add_trace(go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['equity'],
            fill='tozeroy',
            name='Equity',
            line=dict(color='green')
        ))
        
        equity_fig.add_hline(y=initial_capital, line_dash="dash", 
                            annotation_text="Initial Capital", 
                            annotation_position="right")
        
        equity_fig.update_layout(
            title="Equity Curve",
            xaxis_title="Time",
            yaxis_title="Equity ($)",
            hovermode='x unified'
        )
        
        st.plotly_chart(equity_fig, use_container_width=True)
        
        # Trade list
        st.write("### Trade History")
        
        trades_df = df.copy()
        if result['trades']:
            trades_display = []
            for trade in result['trades']:
                trades_display.append({
                    'Entry Time': trade['entry_time'],
                    'Entry Price': f"${trade['entry_price']:.2f}",
                    'Exit Price': f"${trade['exit_price']:.2f}",
                    'Type': trade['position_type'],
                    'P&L': f"${trade['pnl']:.2f}",
                    'P&L %': f"{trade['pnl_pct']:.2f}%"
                })
            
            st.dataframe(trades_display, use_container_width=True)
        
        # Save results
        if st.button("💾 Save Results"):
            run_id = backtest_engine.save_backtest_result(result)
            st.success(f"✅ Results saved with Run ID: {run_id}")


# ============================================================================
# SECTION 3: Multi-Timeframe Comparison
# ============================================================================

def show_multitimeframe_ui():
    """
    Display Multi-Timeframe Analysis
    Shows how trends align across different timeframes
    """
    
    st.subheader("📊 Multi-Timeframe Analysis")
    
    timeframes = ['15m', '1h', '4h', '1d']
    fetcher = BinanceDataFetcher()
    analyzer = MLTrendAnalyzer()
    
    results = {}
    
    # Analyze each timeframe
    with st.spinner("Analyzing timeframes..."):
        for tf in timeframes:
            df_tf = fetcher.fetch_historical_data(tf, limit=200)
            
            if df_tf is not None and not df_tf.empty:
                from app import SMCIndicators
                df_tf = SMCIndicators.engineer_all_features(df_tf)
                
                prediction = analyzer.predict_trend(df_tf)
                regime = analyzer.identify_trend_regime(df_tf)
                
                if prediction and regime:
                    results[tf] = {
                        'trend': prediction['trend'],
                        'confidence': prediction['confidence'],
                        'regime': regime['regime'],
                        'support': regime['support'],
                        'resistance': regime['resistance']
                    }
    
    # Display results in columns
    cols = st.columns(4)
    
    for idx, tf in enumerate(timeframes):
        with cols[idx]:
            st.write(f"### {tf.upper()}")
            
            if tf in results:
                result = results[tf]
                
                # Trend emoji
                if 'Bull' in result['trend']:
                    emoji = '🟢'
                elif 'Bear' in result['trend']:
                    emoji = '🔴'
                else:
                    emoji = '⚫'
                
                st.metric(
                    f"{emoji} Trend",
                    result['trend'].replace(' ', '\n'),
                    f"{result['confidence']:.0%}"
                )
                
                st.write(f"**Regime:** {result['regime']}")
                st.write(f"**Support:** ${result['support']:.2f}")
                st.write(f"**Resistance:** ${result['resistance']:.2f}")
            else:
                st.warning("No data")
    
    # Alignment summary
    st.write("### 🔄 Alignment Summary")
    
    if results:
        all_trends = [r['trend'] for r in results.values()]
        bullish_count = sum(1 for t in all_trends if 'Bull' in t)
        bearish_count = sum(1 for t in all_trends if 'Bear' in t)
        
        alignment = (
            "🟢 Strong Bullish" if bullish_count >= 3 else
            "🔴 Strong Bearish" if bearish_count >= 3 else
            "⚫ Mixed"
        )
        
        st.metric(
            "Overall Alignment",
            alignment,
            f"Bullish: {bullish_count} | Bearish: {bearish_count}"
        )


# ============================================================================
# SECTION 4: Add to Main App
# ============================================================================

"""
To integrate these into your existing app.py, add this to the main UI section:

# In the main tabs area where you have other tabs:

with col1:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Dashboard",
        "🤖 ML Trends",          # NEW
        "⚙️ Settings",
        "📈 Backtesting",         # NEW
        "🧮 Multi-TF",            # NEW
        "📚 Info"
    ])
    
    with tab2:
        show_ml_trend_analysis_ui(fetcher, df, selected_timeframe)
    
    with tab4:
        show_backtesting_ui(df, selected_timeframe)
    
    with tab5:
        show_multitimeframe_ui()

"""

print("✅ Integration code ready!")
print("Copy the functions above into your app.py")
print("Add tab sections to display the ML analysis in Streamlit UI")
