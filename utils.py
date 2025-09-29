# utils.py
import os
import time
import pandas as pd
import numpy as np
import pytz
import requests
import yfinance as yf
import ta
from datetime import datetime
from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, CSV_DIR

IST = pytz.timezone(TIMEZONE)
os.makedirs(CSV_DIR, exist_ok=True)

# --------------------------- TELEGRAM ---------------------------
def send_telegram_message(bot_token, message, chat_ids=None):
    """Send message to provided chat_ids or the hardcoded list."""
    results = {}
    if chat_ids is None:
        chat_ids = TELEGRAM_CHAT_IDS
    chat_ids = [str(c) for c in chat_ids]
    if not bot_token or not chat_ids:
        print("send_telegram_message: missing token or chat ids")
        return results

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            resp = requests.post(url, data=payload, timeout=10)
            try:
                resp_json = resp.json()
                results[chat_id] = {"ok": bool(resp_json.get("ok", False)), "resp": resp_json}
            except Exception:
                results[chat_id] = {"ok": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            results[chat_id] = {"ok": False, "error": str(e)}
    return results

# --------------------------- YFINANCE SAFE FETCH ---------------------------
def safe_yf_download(yf_symbol, period="1d", interval="5m", max_retries=3, sleep_between=1.0):
    """Download yfinance data with retries and fallback to daily."""
    for attempt in range(max_retries):
        try:
            df = yf.download(yf_symbol, period=period, interval=interval, progress=False, threads=False)
            if df is None or df.empty:
                df = yf.download(yf_symbol, period="5d", interval="1d", progress=False, threads=False)
            if df is None or df.empty:
                time.sleep(sleep_between)
                continue
            return df
        except Exception as e:
            print(f"safe_yf_download error for {yf_symbol}: {e}")
            time.sleep(sleep_between)
    return None

def fetch_intraday_yfinance(symbol):
    """Fetch intraday data and save CSV. Returns DataFrame."""
    yf_symbol = f"{symbol}.NS"
    df = safe_yf_download(yf_symbol, period="1d", interval="5m")
    if df is None or df.empty:
        # fallback to previous day CSV if exists
        prev_csv = os.path.join(CSV_DIR, f"{symbol}_prev.csv")
        if os.path.exists(prev_csv):
            df = pd.read_csv(prev_csv)
        else:
            return None
    else:
        df.reset_index(inplace=True)
        df.columns = [c.lower() for c in df.columns]
        if 'adj close' in df.columns and 'close' not in df.columns:
            df.rename(columns={'adj close': 'close'}, inplace=True)
        # Save CSV for fallback
        df.to_csv(os.path.join(CSV_DIR, f"{symbol}_prev.csv"), index=False)
    return df

# --------------------------- INDICATORS ---------------------------
def calculate_indicators(df):
    """Add EMA, RSI, and volume indicators."""
    if df is None or df.empty:
        return df
    df = df.copy()
    if df.shape[0] >= 20:
        df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20, fillna=True).ema_indicator()
    if df.shape[0] >= 50:
        df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50, fillna=True).ema_indicator()
    if df.shape[0] >= 14:
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()
    df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    return df

# --------------------------- ANALYSIS ---------------------------
def get_percent_change(df):
    if df is None or df.empty:
        return 0.0
    first = df['close'].iloc[0]
    last = df['close'].iloc[-1]
    if first == 0:
        return 0.0
    return ((last - first) / first) * 100

def fetch_and_analyze(symbol):
    df = fetch_intraday_yfinance(symbol)
    if df is None:
        return None
    df = calculate_indicators(df)
    pct = get_percent_change(df)
    current_price = df['close'].iloc[-1]
    return {"symbol": symbol, "percent_change": pct, "current_price": current_price, "df": df}

def get_top10_by_percent(symbols):
    results = []
    for s in symbols:
        try:
            info = fetch_and_analyze(s)
            if info:
                results.append(info)
        except Exception as e:
            print(f"Error fetching {s}: {e}")
    results.sort(key=lambda x: x.get('percent_change',0), reverse=True)
    return results[:10]

def send_top10_telegram(symbols):
    top10 = get_top10_by_percent(symbols)
    if not top10:
        return send_telegram_message(TELEGRAM_BOT_TOKEN, "<b>No Top-10 data available</b>")
    message = "<b>🔥 Top 10 Nifty 50 Stocks (by % change) 🔥</b>\n\n"
    for i,s in enumerate(top10,1):
        pct = s.get('percent_change',0.0)
        sign = "+" if pct >=0 else ""
        message += f"{i}. {s['symbol']} | {sign}{pct:.2f}% | ₹{s['current_price']:.2f}\n"
    return send_telegram_message(TELEGRAM_BOT_TOKEN, message)
