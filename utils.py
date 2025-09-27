import pandas as pd
import numpy as np
import pytz
import requests
import json
import os
import ta
import yfinance as yf

from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

IST = pytz.timezone(TIMEZONE)
CHAT_IDS_FILE = "chat_ids.json"

# ---------------------------
# TELEGRAM
# ---------------------------
def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r") as f:
            ids = json.load(f)
            return list(set(ids + TELEGRAM_CHAT_IDS))
    return TELEGRAM_CHAT_IDS.copy()

def save_chat_ids(ids):
    with open(CHAT_IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

def auto_add_new_chats():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    chat_ids = load_chat_ids()
    try:
        r = requests.get(url, timeout=5).json()
        new_ids = []
        for item in r.get("result", []):
            chat_id = str(item["message"]["chat"]["id"])
            if chat_id not in chat_ids:
                chat_ids.append(chat_id)
                new_ids.append(chat_id)
        if new_ids:
            print("New chat IDs added:", new_ids)
            save_chat_ids(chat_ids)
    except Exception as e:
        print("Failed to fetch updates:", e)
    return chat_ids

def send_telegram_message(bot_token, message, chat_ids=None):
    if chat_ids is None:
        chat_ids = load_chat_ids()
    if not bot_token or not chat_ids:
        print("Telegram not configured.")
        return
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, data=payload, timeout=5)
        except Exception as e:
            print("Telegram send failed to", chat_id, e)

# ---------------------------
# YFINANCE DATA
# ---------------------------
def fetch_intraday_yfinance(symbol, period="1d", interval="1m"):
    try:
        df = yf.download(tickers=symbol, period=period, interval=interval, progress=False)
        if df is None or df.empty:
            return None
        df = df.tz_convert(TIMEZONE) if df.index.tzinfo or df.index.tz else df
        df = df.reset_index()
        df.rename(columns={
            "Datetime": "datetime", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        }, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values("datetime").reset_index(drop=True)
        return df
    except Exception as e:
        print("yfinance fetch error", symbol, e)
        return None

# ---------------------------
# INDICATORS
# ---------------------------
def compute_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
    df['vwap'] = vwap
    return df

def calculate_indicators(df):
    df = df.copy()
    try:
        df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
        df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_hist'] = macd.macd_diff()
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_high'] = bb.bollinger_hband()
        df['bb_low'] = bb.bollinger_lband()
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        df['roc'] = ta.momentum.ROCIndicator(df['close'], window=9).roc()
        try:
            stochrsi = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3)
            df['stoch_rsi'] = stochrsi.stochrsi()
        except Exception:
            df['stoch_rsi'] = np.nan
        df = compute_vwap(df)
        df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    except Exception as e:
        print("Indicator calc error:", e)
    return df

# ---------------------------
# COMPOSITE SCORE + SIGNAL
# ---------------------------
def score_stock(df):
    latest = df.iloc[-1]
    score = 0
    try:
        trend_pts = 0
        if latest['ema20'] > latest['ema50']:
            trend_pts += 20
        if latest['macd_hist'] > 0:
            trend_pts += 10
        score += trend_pts
    except: pass

    try:
        mom_pts = 0
        rsi = latest['rsi']
        roc = latest['roc']
        stoch = latest.get('stoch_rsi', np.nan)
        if 30 <= rsi <= 60:
            mom_pts += 12
        elif rsi < 30:
            mom_pts += 8
        elif rsi > 60 and rsi < 75:
            mom_pts += 6
        if not np.isnan(roc) and roc > 0:
            mom_pts += 5
        if not np.isnan(stoch) and stoch < 0.5:
            mom_pts += 3
        score += mom_pts
    except: pass

    try:
        vol_pts = 0
        if latest['volume'] > 1.5 * latest['vol_avg_20']:
            vol_pts = 15
        elif latest['volume'] > 1.1 * latest['vol_avg_20']:
            vol_pts = 8
        score += vol_pts
    except: pass

    try:
        if latest['close'] > latest['vwap']:
            score += 10
    except: pass

    try:
        if latest['adx'] > 25:
            score += 10
        elif latest['adx'] > 18:
            score += 5
    except: pass

    try:
        obv = df['obv']
        if len(obv) >= 21:
            if obv.iloc[-1] > obv.rolling(20).mean().iloc[-1]:
                score += 5
    except: pass

    try:
        atr_rel = latest['atr'] / latest['close'] if latest['close'] and latest['atr'] else 0
        if atr_rel < 0.01:
            score += 5
        elif atr_rel < 0.02:
            score += 3
    except: pass

    score = max(0, min(100, int(score)))
    return score

def classify_signal(score, df):
    latest = df.iloc[-1]
    try:
        if latest['close'] < latest['bb_low']:
            return "STRONG SELL"
        if latest['rsi'] > 85:
            return "STRONG SELL"
    except: pass

    if score >= 70:
        return "STRONG BUY"
    if score >= 55:
        return "BUY"
    if score >= 40:
        return "HOLD"
    return "SELL"

# ---------------------------
# HELPER WRAPPER
# ---------------------------
def fetch_and_analyze(symbol_yf, trend_minutes=30):
    df = fetch_intraday_yfinance(symbol_yf, period="1d", interval="1m")
    if df is None or df.empty:
        return None
    df = calculate_indicators(df)
    score = score_stock(df)
    signal = classify_signal(score, df)

    if len(df) > trend_minutes:
        past_price = df['close'].iloc[-trend_minutes]
        future_potential = (df['close'].iloc[-1] - past_price) / past_price * 100
    else:
        future_potential = 0.0

    return {
        "symbol": symbol_yf,
        "score": score,
        "signal": signal,
        "current_price": float(df['close'].iloc[-1]),
        "datetime": str(df['datetime'].iloc[-1]),
        "future_potential": future_potential,
        "df": df
    }
