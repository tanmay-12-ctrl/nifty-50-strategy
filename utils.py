import time
import pandas as pd
import numpy as np
import pytz
import requests
import os
import yfinance as yf
import ta
from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

IST = pytz.timezone(TIMEZONE)
CSV_DIR = "daily_csv"
os.makedirs(CSV_DIR, exist_ok=True)

# ---------------- TELEGRAM ----------------
def send_telegram_message(bot_token, message, chat_ids=None):
    results = {}
    if chat_ids is None:
        chat_ids = TELEGRAM_CHAT_IDS
    for chat_id in chat_ids:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10
            )
            try:
                resp_json = resp.json()
                results[chat_id] = {"ok": resp_json.get("ok", False), "resp": resp_json}
            except:
                results[chat_id] = {"ok": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            results[chat_id] = {"ok": False, "error": str(e)}
    return results

# ---------------- YFINANCE SAFE FETCH ----------------
def safe_yf_download(yf_symbol, period="1d", interval="5m", max_retries=2, sleep_between=1.0):
    for attempt in range(max_retries):
        try:
            df = yf.download(yf_symbol, period=period, interval=interval, progress=False, threads=False)
            if df is None or df.empty:
                df = yf.download(yf_symbol, period="5d", interval="1d", progress=False, threads=False)
            if df is None or df.empty:
                time.sleep(sleep_between)
                continue
            return df
        except Exception:
            time.sleep(sleep_between)
            continue
    return None

def fetch_intraday_yfinance(symbol, period="1d", interval="5m"):
    yf_symbol = f"{symbol}.NS"
    df = safe_yf_download(yf_symbol, period=period, interval=interval, max_retries=3, sleep_between=0.8)
    if df is None or df.empty:
        # fallback to previous day's CSV
        csv_path = os.path.join(CSV_DIR, f"{yf_symbol}_latest.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
        else:
            return None
    else:
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        if 'adj close' in df.columns and 'close' not in df.columns:
            df = df.rename(columns={'adj close': 'close'})
        for col in ["datetime","open","high","low","close","volume"]:
            if col not in df.columns:
                df[col] = np.nan
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values("datetime").dropna(subset=["close"]).reset_index(drop=True)
        df.to_csv(os.path.join(CSV_DIR, f"{yf_symbol}_latest.csv"), index=False)
    return df[["datetime","open","high","low","close","volume"]]

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    try:
        if df.shape[0] < 3:
            return df
        df = df.copy()
        if df.shape[0] >= 20:
            df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
            df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        if df.shape[0] >= 14:
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    except:
        pass
    return df

# ---------------- PERCENT CHANGE ----------------
def get_percent_change(df):
    try:
        if df is None or df.empty:
            return 0.0
        first = float(df['close'].iloc[0])
        last = float(df['close'].iloc[-1])
        if first == 0: return 0.0
        return ((last - first)/first)*100.0
    except:
        return 0.0

# ---------------- FETCH & ANALYZE ----------------
def fetch_and_analyze(symbol):
    df = fetch_intraday_yfinance(symbol)
    if df is None or df.empty:
        return None
    df = calculate_indicators(df)
    pct = get_percent_change(df)
    current_price = float(df['close'].iloc[-1])
    return {"symbol": symbol, "percent_change": pct, "current_price": current_price, "df": df}

# ---------------- TOP 10 ----------------
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
        msg = "<b>No Top-10 data available right now</b>"
        return send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
    message = "<b>🔥 Top 10 Nifty 50 Stocks (by % change) 🔥</b>\n\n"
    for i,s in enumerate(top10,1):
        pct = s.get('percent_change',0.0)
        sign = "+" if pct>=0 else ""
        message += f"{i}. {s['symbol']} | {sign}{pct:.2f}% | ₹{s['current_price']:.2f}\n"
    return send_telegram_message(TELEGRAM_BOT_TOKEN, message)
