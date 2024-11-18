import time
import pandas as pd
import pandas_ta as ta
import requests
import logging
from dotenv import load_dotenv
import os
import hmac
import hashlib
import base64
import json

# Cài đặt logging
logging.basicConfig(level=logging.INFO, filename='bot.log', 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Tải biến môi trường
load_dotenv()
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
PASSPHRASE = os.getenv('PASSPHRASE')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
BASE_URL = 'https://www.okx.com'

def send_telegram_message(message):
    try:
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logging.error(f"Telegram API Error: {response.text}")
    except Exception as e:
        logging.error(f"Exception in send_telegram_message: {e}")

def get_candles(symbol, timeframe='1m', limit=100):
    try:
        endpoint = '/api/v5/market/candles'
        params = {
            'instId': symbol,
            'bar': timeframe,
            'limit': limit
        }
        response = requests.get(BASE_URL + endpoint, params=params)
        data = response.json()
        if data['code'] == '0':
            candles = data['data']
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df
        else:
            logging.error(f"Lỗi khi lấy dữ liệu nến: {data}")
            return None
    except Exception as e:
        logging.error(f"Exception trong get_candles: {e}")
        return None

def get_headers(method, request_path, body=''):
    try:
        timestamp = str(time.time())
        message = timestamp + method + request_path + body
        hmac_key = base64.b64decode(SECRET_KEY)
        signature = hmac.new(hmac_key, message.encode('utf-8'), hashlib.sha256).digest()
        signature = base64.b64encode(signature).decode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'OK-ACCESS-KEY': API_KEY,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': PASSPHRASE
        }
        return headers
    except Exception as e:
        logging.error(f"Exception trong get_headers: {e}")
        return {}

def place_order(instId, side, size, price=None, orderType='limit'):
    try:
        endpoint = '/api/v5/trade/order'
        url = BASE_URL + endpoint
        body = {
            "instId": instId,
            "tdMode": "cash",
            "side": side,
            "ordType": orderType,
            "sz": size
        }
        if orderType == 'limit' and price:
            body['px'] = str(price)
        body_json = json.dumps(body)
        headers = get_headers('POST', endpoint, body_json)
        response = requests.post(url, headers=headers, data=body_json)
        data = response.json()
        if data['code'] == '0':
            logging.info(f"Đặt lệnh thành công: {data}")
            send_telegram_message(f"Đặt lệnh {'mua' if side == 'buy' else 'bán'} {instId} tại giá {price}")
        else:
            logging.error(f"Lỗi khi đặt lệnh: {data}")
            send_telegram_message(f"Lỗi khi đặt lệnh: {data}")
        return data
    except Exception as e:
        logging.error(f"Exception trong place_order: {e}")
        return None

def generate_signals(df):
    df['signal'] = 0
    # Điều kiện mua: RSI < 30 và MACD > Signal Line
    df['signal'][(df['RSI'] < 30) & (df['MACD'] > df['MACD_Signal'])] = 1
    # Điều kiện bán: RSI > 70 và MACD < Signal Line
    df['signal'][(df['RSI'] > 70) & (df['MACD'] < df['MACD_Signal'])] = -1
    df['position'] = df['signal'].diff()
    return df

def main():
    symbol = 'BTC-USDT'
    while True:
        df = get_candles(symbol, timeframe='1m', limit=100)
        if df is not None:
            # Tính toán chỉ số RSI và MACD
            df['RSI'] = ta.rsi(df['close'], length=14)
            macd = ta.macd(df['close'])
            df['MACD'] = macd['MACD_12_26_9']
            df['MACD_Signal'] = macd['MACDs_12_26_9']
            df['MACD_Hist'] = macd['MACDh_12_26_9']
            
            # Đưa ra tín hiệu
            df = generate_signals(df)
            latest_signal = df['signal'].iloc[-1]
            latest_price = df['close'].iloc[-1]
            
            if latest_signal == 1:
                # Đặt lệnh mua
                order_response = place_order(symbol, 'buy', '0.001', price=latest_price, orderType='limit')
            elif latest_signal == -1:
                # Đặt lệnh bán
                order_response = place_order(symbol, 'sell', '0.001', price=latest_price, orderType='limit')
        
        # Chờ đến lần kiểm tra tiếp theo
        time.sleep(60)

if __name__ == "__main__":
    main()
