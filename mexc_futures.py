import ccxt
import pandas as pd
import requests
import time
from datetime import datetime

# ====== CONFIGURATION ======
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1367574351330803824/1epkOlLe3qba1bladexGraGlv_5T6lzlxhPxdgNQf0RX6eTGxb9bBI5kv8DlzpO8MOIx"
TIMEFRAME = '5m'
SCAN_INTERVAL = 300  # 5 minutes in seconds
MAX_PAIRS = 50  # Limit to prevent API rate limits
MIN_VOLUME = 100000  # Minimum 24h volume in USDT

# EMA Periods Configuration
EMA_PERIODS = {
    'fast': 7,
    'medium': 21,
    'slow': 50,
    'very_slow': 200
}

# ====== INITIALIZE EXCHANGE ======
def initialize_exchange():
    exchange = ccxt.mexc({
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True
        },
        'enableRateLimit': True,
        'timeout': 30000,  # 30 seconds timeout
    })
    
    # Enhanced time synchronization with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # First try normal time sync
            if attempt == 0:
                exchange.load_markets()
                break
            
            # If first attempt fails, manually set time difference
            elif attempt == 1:
                print("⚠️ Time sync failed, attempting manual adjustment...")
                exchange.options['timeDifference'] = 0
                exchange.load_markets()
                break
                
            # If still failing, disable time sync completely
            elif attempt == 2:
                print("⚠️ Manual adjustment failed, disabling time sync...")
                exchange.options['adjustForTimeDifference'] = False
                exchange.load_markets()
                break
                
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                raise Exception("Failed to initialize exchange after multiple attempts")
            time.sleep(2)  # Wait before retrying
    
    return exchange

exchange = initialize_exchange()

# ====== DISCORD ALERTS ======
def send_alert(message, is_buy=True):
    color = 0x00FF00 if is_buy else 0xFF0000  # Green for buy, red for sell
    embed = {
        "title": "MEXC Futures Alert",
        "description": message,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {
            "text": "5-Minute EMA Scanner"
        }
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    except Exception as e:
        print(f"Alert failed: {e}")

# ====== FETCH FUTURES PAIRS ======
def get_futures_pairs():
    try:
        markets = exchange.load_markets()
        return [
            symbol for symbol in markets 
            if (markets[symbol]['future'] and 
                markets[symbol]['active'] and
                markets[symbol]['quote'] == 'USDT' and
                markets[symbol].get('info', {}).get('volume24h', 0) > MIN_VOLUME)
        ][:MAX_PAIRS]
    except Exception as e:
        print(f"Error loading markets: {e}")
        return []  # Return empty list if error occurs

# ====== CALCULATE EMAs ======
def calculate_emas(df):
    for name, span in EMA_PERIODS.items():
        df[f'ema{span}'] = df['close'].ewm(span=span, adjust=False).mean()
    return df

# ====== TRADINGVIEW EMA STRATEGY ======
def check_signals():
    print(f"\n=== MEXC 5-MIN FUTURES SCANNER ===")
    print(f"🔍 Scanning at {datetime.now().strftime('%H:%M:%S')}")
    
    for pair in get_futures_pairs():
        try:
            # Get 5m candle data (250 for EMA200)
            ohlcv = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=250)
            if not ohlcv or len(ohlcv) < 50:  # Skip if not enough data
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_emas(df)
            
            # Current values
            current_close = df['close'].iloc[-1]
            ema7 = df['ema7'].iloc[-1]
            ema21 = df['ema21'].iloc[-1]
            ema50 = df['ema50'].iloc[-1]
            ema200 = df['ema200'].iloc[-1]
            
            # Previous values
            prev_ema7 = df['ema7'].iloc[-2]
            prev_ema50 = df['ema50'].iloc[-2]
            
            # TradingView Strategy Conditions
            buy = (ema7 > ema50) and \
                  (prev_ema7 <= prev_ema50) and \
                  (ema7 < ema200) and \
                  (ema21 < ema200) and \
                  (ema50 < ema200) and \
                  (current_close > ema7)  # Price above fast EMA
                  
            sell = (ema7 < ema50) and \
                   (prev_ema7 >= prev_ema50) and \
                   (current_close < ema7)  # Price below fast EMA
            
            # Generate simplified alerts
            if buy:
                alert = f"✅ 🚀 LONG {pair.split(':')[0]}\nPrice: ${current_close:.2f}"
                print(alert)
                send_alert(alert, is_buy=True)
                
            elif sell:
                alert = f"✅ 🔻 SHORT {pair.split(':')[0]}\nPrice: ${current_close:.2f}"
                print(alert)
                send_alert(alert, is_buy=False)
                
        except ccxt.NetworkError as e:
            print(f"⚠️ Network error on {pair}: {str(e)}")
            time.sleep(10)
        except ccxt.ExchangeError as e:
            print(f"⚠️ Exchange error on {pair}: {str(e)}")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Unexpected error on {pair}: {str(e)}")
            time.sleep(2)

# ====== MAIN LOOP ======
if __name__ == "__main__":
    send_alert("🟢 5-MIN FUTURES SCANNER ACTIVATED", is_buy=None)
    
    while True:
        start_time = time.time()
        check_signals()
        elapsed = time.time() - start_time
        sleep_time = max(0, SCAN_INTERVAL - elapsed)
        print(f"⏳ Next scan in {sleep_time:.1f} seconds")
        time.sleep(sleep_time)