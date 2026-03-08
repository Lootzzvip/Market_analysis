# This is the complete recommendations section code
# It will be manually integrated into app.py

recommendation_code = '''
    # ========================================================================
    # TRADE RECOMMENDATIONS SECTION - ALL TIMEFRAMES
    # ========================================================================
    
    st.markdown("---")
    st.subheader("💡 **Trade Recommendations Across All Timeframes**")
    st.markdown("*Real-time analysis of ALL timeframes to find the best trading opportunities*")
    
    # Analyze ALL timeframes for trade opportunities
    all_recommendations = []
    
    for tf_scan in all_timeframes:
        try:
            # Fetch data for this timeframe
            df_tf_rec = fetcher.fetch_historical_data(timeframe=tf_scan, limit=candle_limit.get(tf_scan, 500))
            
            if df_tf_rec is None or len(df_tf_rec) < 5:
                continue
            
            # Apply timeframe-specific confluence threshold
            tf_confluence_map = {
                '1w': max(20, min_confluence_threshold - 25),
                '1d': max(25, min_confluence_threshold - 20),
                '4h': max(30, min_confluence_threshold - 15),
                '2h': min_confluence_threshold - 10,
                '1h': min_confluence_threshold,
                '15m': min_confluence_threshold + 5,
                '5m': min_confluence_threshold + 15
            }
            tf_min_conf = tf_confluence_map.get(tf_scan, min_confluence_threshold)
            
            # Apply SMC features
            df_tf_rec = SMCIndicators.engineer_all_features(
                df_tf_rec,
                htf_bias=combined_bias,
                min_confluence_threshold=tf_min_conf
            )
            
            # Analyze latest candle
            latest_candle = df_tf_rec.iloc[-1]
            current_price = latest_candle['close']
            fvg_type = latest_candle.get('fvg_type', 'none')
            fvg_valid = latest_candle.get('fvg_valid', False)
            confluence_score = latest_candle.get('fvg_confluence_score', 0)
            rsi_value = latest_candle.get('rsi', 50)
            bos_bullish = latest_candle.get('bos_bullish', False)
            bos_bearish = latest_candle.get('bos_bearish', False)
            ob_bullish = latest_candle.get('order_block_bullish', False)
            ob_bearish = latest_candle.get('order_block_bearish', False)
            adx = latest_candle.get('adx', 0)
            
            # Initialize recommendation variables
            recommendation = "WAIT"
            trade_direction = None
            entry_price = None
            stop_loss = None
            take_profit = None
            reasons = []
            warnings = []
            confidence_level = "LOW"
            priority_score = 0
            
            # BUY setup analysis
            if fvg_type == 'bullish' and fvg_valid and confluence_score >= tf_min_conf and bos_bullish:
                if combined_bias >= 0:
                    recommendation = "STRONG BUY"
                    trade_direction = "BUY"
                    confidence_level = "HIGH"
                    priority_score = 100 + confluence_score
                else:
                    recommendation = "BUY (Caution)"
                    trade_direction = "BUY"
                    confidence_level = "MEDIUM"
                    priority_score = 70 + confluence_score
                    warnings.append("⚠️ Counter-trend (HTF Bearish)")
                
                entry_price = current_price
                fvg_gap_low = latest_candle.get('fvg_gap_low', current_price * 0.998)
                stop_loss = fvg_gap_low * 0.998
                risk_distance = entry_price - stop_loss
                take_profit = entry_price + (risk_distance * 2.5)
                
                reasons.append(f"✅ Bullish FVG (Score: {confluence_score:.0f})")
                reasons.append(f"✅ Bullish BOS confirmed")
                if ob_bullish:
                    reasons.append(f"✅ Bullish Order Block")
                if rsi_value < 50:
                    reasons.append(f"✅ RSI {rsi_value:.1f} - upside room")
                if adx > 25:
                    reasons.append(f"✅ Strong trend (ADX {adx:.1f})")
            
            # SELL setup analysis
            elif fvg_type == 'bearish' and fvg_valid and confluence_score >= tf_min_conf and bos_bearish:
                if combined_bias <= 0:
                    recommendation = "STRONG SELL"
                    trade_direction = "SELL"
                    confidence_level = "HIGH"
                    priority_score = 100 + confluence_score
                else:
                    recommendation = "SELL (Caution)"
                    trade_direction = "SELL"
                    confidence_level = "MEDIUM"
                    priority_score = 70 + confluence_score
                    warnings.append("⚠️ Counter-trend (HTF Bullish)")
                
                entry_price = current_price
                fvg_gap_high = latest_candle.get('fvg_gap_high', current_price * 1.002)
                stop_loss = fvg_gap_high * 1.002
                risk_distance = stop_loss - entry_price
                take_profit = entry_price - (risk_distance * 2.5)
                
                reasons.append(f"✅ Bearish FVG (Score: {confluence_score:.0f})")
                reasons.append(f"✅ Bearish BOS confirmed")
                if ob_bearish:
                    reasons.append(f"✅ Bearish Order Block")
                if rsi_value > 50:
                    reasons.append(f"✅ RSI {rsi_value:.1f} - downside room")
                if adx > 25:
                    reasons.append(f"✅ Strong trend (ADX {adx:.1f})")
            
            # Store recommendation if valid
            if trade_direction:
                all_recommendations.append({
                    'timeframe': tf_scan.upper(),
                    'recommendation': recommendation,
                    'direction': trade_direction,
                    'confidence': confidence_level,
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'reasons': reasons,
                    'warnings': warnings,
                    'priority': priority_score,
                    'confluence': confluence_score
                })
        
        except Exception as e:
            continue
    
    # Sort by priority (best trades first)
    all_recommendations.sort(key=lambda x: x['priority'], reverse=True)
    
    # Display recommendations
    if all_recommendations:
        st.success(f"### 🎯 {len(all_recommendations)} Trading Opportunities Found!")
        
        for idx, rec in enumerate(all_recommendations[:5]):  # Show top 5
            with st.expander(f"{'🟢' if 'BUY' in rec['direction'] else '🔴'} **{rec['timeframe']}** - {rec['recommendation']} ({rec['confidence']} Confidence)", expanded=(idx == 0)):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### 📊 **Trade Setup**")
                    st.metric("💰 Entry", f"${rec['entry']:,.2f}")
                    st.metric("🛡️ Stop Loss", f"${rec['stop_loss']:,.2f}")
                    st.metric("🎯 Take Profit", f"${rec['take_profit']:,.2f}")
                    
                    rr = abs(rec['take_profit'] - rec['entry']) / abs(rec['entry'] - rec['stop_loss'])
                    st.metric("📈 R:R Ratio", f"1:{rr:.2f}")
                    
                    # Position size (1% risk)
                    account_balance = st.session_state.trade_executor.balance
                    risk_amt = account_balance * 0.01
                    pos_size = risk_amt / abs(rec['entry'] - rec['stop_loss']) if rec['stop_loss'] != rec['entry'] else 0
                    st.metric("💼 Position Size", f"{pos_size:.4f} BTC", f"1% risk = ${risk_amt:,.2f}")
                
                with col2:
                    st.markdown("#### 🔍 **Why This Trade?**")
                    for reason in rec['reasons']:
                        st.markdown(reason)
                    
                    if rec['warnings']:
                        st.markdown("#### ⚠️ **Warnings**")
                        for warning in rec['warnings']:
                            st.markdown(warning)
    else:
        st.warning("### ⏳ No Trade Setups Found Across Any Timeframe")
        st.info("💡 Waiting for valid FVG + BOS confirmation with sufficient confluence")
    
    st.markdown("---")
'''
