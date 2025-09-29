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

# ---------------- TELEGRAM ----------------
def send_telegram_message(bot_token, message, chat_ids=None):
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
            results[chat_id] = {"ok": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            results[chat_id] = {"ok": False, "error": str(e)}
    return results

# ---------------- YFINANCE ----------------
def safe_yf_download(symbol, period="1d", interval="5m"):
    """Retry download, fallback to daily 5d if empty."""
    for attempt in range(3):
        try:
            df = yf.download(symbol, period=period, interval=interval, progress=False, threads=False)
            if df is not None and not df.empty:
                return df
        except:
            time.sleep(1)
    # fallback to daily 5d
    try:
        df = yf.download(symbol, period="5d", interval="1d", progress=False, threads=False)
        if df is not None and not df.empty:
            return df
    except:
        pass
    return None

def fetch_intraday(symbol):
    yf_symbol = f"{symbol}.NS" if ".NS" not in symbol else symbol
    df = safe_yf_download(yf_symbol)
    if df is None or df.empty:
        # fallback: try previous day CSV
        csv_path = os.path.join(CSV_DIR, f"{symbol}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, parse_dates=['Datetime'])
        else:
            return None
    else:
        df = df.reset_index()
        df.rename(columns={c.lower(): c.lower() for c in df.columns}, inplace=True)
        if 'adj close' in df.columns and 'close' not in df.columns:
            df.rename(columns={'adj close': 'close'}, inplace=True)
        df.to_csv(os.path.join(CSV_DIR, f"{symbol}.csv"), index=False)
    return df

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    try:
        if df.shape[0] >= 20:
            df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
        if df.shape[0] >= 50:
            df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        if df.shape[0] >= 14:
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    except:
        pass
    return df

# ---------------- ANALYSIS ----------------
def percent_change(df):
    if df is None or df.empty:
        return 0.0
    first = df['close'].iloc[0]
    last = df['close'].iloc[-1]
    if first == 0:
        return 0.0
    return ((last - first) / first) * 100

def fetch_and_analyze(symbol):
    df = fetch_intraday(symbol)
    if df is None:
        return None
    df = calculate_indicators(df)
    pct = percent_change(df)
    current_price = df['close'].iloc[-1]
    return {"symbol": symbol, "df": df, "percent_change": pct, "current_price": current_price}

def get_top10_by_percent(symbols):
    results = []
    for s in symbols:
        info = fetch_and_analyze(s)
        if info:
            results.append(info)
    results.sort(key=lambda x: x['percent_change'], reverse=True)
    return results[:10]

def send_top10_telegram(symbols):
    top10 = get_top10_by_percent(symbols)
    if not top10:
        msg = "<b>No Top-10 data available (market closed / yfinance empty)</b>"
        return send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
    message = "<b>🔥 Top 10 Nifty50 Stocks 🔥</b>\n\n"
    for i, s in enumerate(top10, 1):
        pct = s['percent_change']
        sign = "+" if pct >= 0 else ""
        message += f"{i}. {s['symbol']} | {sign}{pct:.2f}% | ₹{s['current_price']:.2f}\n"
    return send_telegram_message(TELEGRAM_BOT_TOKEN, message)
