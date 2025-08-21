import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta
import numpy as np
import logging
import uuid

# Configure logging for notifications
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize MetaTrader 5
def initialize_mt5():
    if not mt5.initialize():
        logger.error("MetaTrader5 initialization failed")
        return False
    logger.info("MetaTrader5 initialized successfully")
    return True

# Fetch historical data for a currency pair
def fetch_data(symbol, timeframe, num_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None or len(rates) == 0:
        logger.error(f"Failed to fetch data for {symbol}")
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# Calculate ATR for volatility
def calculate_atr(df, period=14):
    df['high_low'] = df['high'] - df['low']
    df['high_prev_close'] = abs(df['high'] - df['close'].shift(1))
    df['low_prev_close'] = abs(df['low'] - df['close'].shift(1))
    df['true_range'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
    df['atr'] = df['true_range'].rolling(window=period).mean()
    return df['atr'].iloc[-1]

# Calculate percentage price change
def calculate_price_change(df):
    current_price = df['close'].iloc[-1]
    previous_price = df['close'].iloc[0]
    return ((current_price - previous_price) / previous_price) * 100

# Detect smart money activity (volume spikes and reversals)
def detect_smart_money(df, volume_threshold=1.5, reversal_threshold=0.0003):
    avg_volume = df['tick_volume'].rolling(window=14).mean().iloc[-1]
    current_volume = df['tick_volume'].iloc[-1]
    volume_spike = current_volume > (avg_volume * volume_threshold)
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    current_close = df['close'].iloc[-1]
    bullish_reversal = (df['low'].iloc[-1] <= prev_low and 
                       current_close >= prev_high - reversal_threshold and 
                       current_close > df['open'].iloc[-1])
    bearish_reversal = (df['high'].iloc[-1] >= prev_high and 
                        current_close <= prev_low + reversal_threshold and 
                        current_close < df['open'].iloc[-1])
    smart_money_detected = volume_spike and (bullish_reversal or bearish_reversal)
    return {
        'smart_money': smart_money_detected,
        'volume_spike': volume_spike,
        'bullish_reversal': bullish_reversal,
        'bearish_reversal': bearish_reversal
    }

# Select the top three pairs to trade, avoiding clustering
def select_top_three_pairs(pair_volatility, thresholds):
    if not pair_volatility:
        return []
    
    # Calculate scores for each pair
    atr_values = [metrics['atr'] for metrics in pair_volatility.values()]
    price_change_values = [abs(metrics['price_change']) for metrics in pair_volatility.values()]
    atr_range = max(atr_values) - min(atr_values) if max(atr_values) != min(atr_values) else 1
    price_change_range = max(price_change_values) - min(price_change_values) if max(price_change_values) != min(price_change_values) else 1
    
    pair_scores = []
    for symbol, metrics in pair_volatility.items():
        if metrics['atr'] < thresholds['atr'] and abs(metrics['price_change']) < thresholds['price_change']:
            continue
        normalized_atr = (metrics['atr'] - min(atr_values)) / atr_range
        normalized_price_change = (abs(metrics['price_change']) - min(price_change_values)) / price_change_range
        score = (0.5 * normalized_atr) + (0.3 * normalized_price_change)
        if metrics['smart_money']:
            score += 0.2
        pair_scores.append({
            'symbol': symbol,
            'score': score,
            'atr': metrics['atr'],
            'price_change': metrics['price_change'],
            'smart_money': metrics['smart_money']
        })
    
    if not pair_scores:
        return []
    
    # Sort by score and ATR (tiebreaker)
    pair_scores.sort(key=lambda x: (x['score'], x['atr']), reverse=True)
    
    # Select top three pairs, avoiding clustering
    selected_pairs = []
    used_currencies = set()
    for pair in pair_scores:
        if len(selected_pairs) >= 3:
            break
        base, quote = pair['symbol'][:3], pair['symbol'][3:-1] if pair['symbol'].endswith('m') else pair['symbol'][3:]
        if base not in used_currencies and quote not in used_currencies:
            selected_pairs.append(pair)
            used_currencies.add(base)
            used_currencies.add(quote)
    
    return selected_pairs

# Rank currencies by aggregated volatility and check for smart money
def rank_currencies(currency_pairs, timeframe, num_bars):
    currency_volatility = {}
    pair_volatility = {}
    
    for symbol in currency_pairs:
        df = fetch_data(symbol, timeframe, num_bars)
        if df is None:
            continue
        atr = calculate_atr(df)
        price_change = calculate_price_change(df)
        smart_money_metrics = detect_smart_money(df)
        pair_volatility[symbol] = {
            'atr': atr,
            'price_change': price_change,
            'smart_money': smart_money_metrics['smart_money'],
            'volume_spike': smart_money_metrics['volume_spike'],
            'bullish_reversal': smart_money_metrics['bullish_reversal'],
            'bearish_reversal': smart_money_metrics['bearish_reversal']
        }
        base, quote = symbol[:3], symbol[3:-1] if symbol.endswith('m') else symbol[3:]
        for currency in [base, quote]:
            if currency not in currency_volatility:
                currency_volatility[currency] = {'total_atr': 0, 'count': 0}
            currency_volatility[currency]['total_atr'] += atr
            currency_volatility[currency]['count'] += 1
    
    for currency in currency_volatility:
        currency_volatility[currency]['avg_atr'] = (
            currency_volatility[currency]['total_atr'] / currency_volatility[currency]['count']
        )
    
    ranked_currencies = sorted(
        currency_volatility.items(),
        key=lambda x: x[1]['avg_atr'],
        reverse=True
    )
    
    return ranked_currencies, pair_volatility

# Check for notification triggers, ensuring at least three high activity pairs
def check_notifications(pair_volatility, thresholds):
    notifications = []
    
    # Collect high activity pairs
    high_activity_pairs = []
    for symbol, metrics in pair_volatility.items():
        if metrics['atr'] > thresholds['atr'] or abs(metrics['price_change']) > thresholds['price_change']:
            high_activity_pairs.append({
                'symbol': symbol,
                'atr': metrics['atr'],
                'price_change': metrics['price_change']
            })
    
    # Sort by ATR to prioritize most volatile pairs
    high_activity_pairs.sort(key=lambda x: x['atr'], reverse=True)
    
    # Select at least three pairs (or more if tied)
    selected_high_activity = []
    if high_activity_pairs:
        third_atr = high_activity_pairs[min(2, len(high_activity_pairs) - 1)]['atr'] if len(high_activity_pairs) >= 3 else high_activity_pairs[-1]['atr']
        for pair in high_activity_pairs:
            if len(selected_high_activity) < 3 or pair['atr'] >= third_atr:
                selected_high_activity.append(pair)
            else:
                break
    
    # Add high activity notifications
    for pair in selected_high_activity:
        message = (
            f"High activity detected in {pair['symbol']}: "
            f"ATR={pair['atr']:.5f}, Price Change={pair['price_change']:.2f}%"
        )
        notifications.append(message)
    
    # Add smart money notifications (not limited)
    for symbol, metrics in pair_volatility.items():
        if metrics['smart_money']:
            reversal_type = "Bullish" if metrics['bullish_reversal'] else "Bearish"
            message = (
                f"Smart money activity detected in {symbol}: "
                f"{reversal_type} reversal with volume spike"
            )
            notifications.append(message)
    
    # If fewer than three high activity pairs, log a note
    if len(selected_high_activity) < 3:
        notifications.append(f"Note: Only {len(selected_high_activity)} high activity pair(s) detected")
    
    return notifications

# Main monitoring function
def monitor_forex(currency_pairs, thresholds, interval=1800):
    if not initialize_mt5():
        return
    
    timeframes = {
        '30min': (mt5.TIMEFRAME_M30, 14),
        '2hour': (mt5.TIMEFRAME_H2, 14)
    }
    
    try:
        while True:
            for timeframe_name, (timeframe, num_bars) in timeframes.items():
                logger.info(f"Monitoring {timeframe_name} timeframe...")
                
                ranked_currencies, pair_volatility = rank_currencies(currency_pairs, timeframe, num_bars)
                
                # Select top three pairs to trade
                top_three_pairs = select_top_three_pairs(pair_volatility, thresholds)
                if top_three_pairs:
                    logger.info(f"Best pair to trade ({timeframe_name}):")
                    for pair in top_three_pairs:
                        smart_money_flag = " (Smart Money)" if pair['smart_money'] else ""
                        logger.info(
                            f"{pair['symbol']}: Score={pair['score']:.3f}, "
                            f"ATR={pair['atr']:.5f}, Price Change={pair['price_change']:.2f}%{smart_money_flag}"
                        )
                else:
                    logger.info(f"No suitable pairs to trade ({timeframe_name})")
                
                logger.info(f"Top active currencies ({timeframe_name}):")
                for currency, metrics in ranked_currencies[:3]:
                    logger.info(f"{currency}: Avg ATR={metrics['avg_atr']:.5f}")
                
                notifications = check_notifications(pair_volatility, thresholds)
                for notification in notifications:
                    logger.info(notification)
                
                logger.info(f"Active pairs ({timeframe_name}):")
                for symbol, metrics in sorted(
                    pair_volatility.items(),
                    key=lambda x: x[1]['atr'],
                    reverse=True
                )[:5]:
                    smart_money_flag = " (Smart Money)" if metrics['smart_money'] else ""
                    logger.info(
                        f"{symbol}: ATR={metrics['atr']:.5f}, "
                        f"Price Change={metrics['price_change']:.2f}%{smart_money_flag}"
                    )
            
            logger.info(f"Waiting {interval} seconds before next check...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    finally:
        mt5.shutdown()

# Example usage
if __name__ == "__main__":
    currency_pairs = [
        "EURUSDm", "EURGBPm","EURCHFm","EURCADm","EURNZDm", "EURJPYm","EURAUDm",
        "GBPUSDm", "GBPJPYm","GBPCHFm","GBPAUDm","GBPNZDm","GBPCADm",
        "AUDUSDm", "AUDNZDm","AUDCADm","AUDJPYm", "AUDCHFm",
        "NZDUSDm","NZDJPYm","NZDCHFm","NZDCADm"
        "USDCADm", "USDCHFm", "USDJPYm",
        "CHFJPYm", "CADCHFm","CADJPYm",
    ]
    thresholds = {
        'atr': 0.0006,
        'price_change': 0.5
    }
    monitor_forex(currency_pairs, thresholds, interval=1800)