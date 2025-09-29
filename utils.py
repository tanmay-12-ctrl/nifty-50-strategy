# utils.py (UPDATED)
import pandas as pd
import numpy as np
import pytz
import requests
import json
import os
import ta
import yfinance as yf
import math
from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

IST = pytz.timezone(TIMEZONE)
CHAT_IDS_FILE = "chat_ids.json"

# --------------------------- TELEGRAM ---------------------------
def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r") as f:
            ids = json.load(f)
            ids = [str(i) for i in ids]
            cfg_ids = [str(i) for i in (TELEGRAM_CHAT_IDS or [])]
            return list(dict.fromkeys(ids + cfg_ids))
    return [str(i) for i in (TELEGRAM_CHAT_IDS or [])]

def save_chat_ids(ids):
    ids = [str(i) for i in ids]
    with open(CHAT_IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

def auto_add_new_chats():
    if not TELEGRAM_BOT_TOKEN:
        return load_chat_ids()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    chat_ids = load_chat_ids()
    try:
        r = requests.get(url, timeout=6).json()
        for item in r.get("result", []):
            msg = item.get("message") or item.get("edited_message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id and str(chat_id) not in chat_ids:
                chat_ids.append(str(chat_id))
        save_chat_ids(chat_ids)
    except Exception as e:
        print("auto_add_new_chats failed:", e)
    return chat_ids

def send_telegram_message(bot_token, message, chat_ids=None):
    results = {}
    if chat_ids is None:
        chat_ids = load_chat_ids()
    chat_ids = [str(c) for c in (chat_ids or [])]
    if not bot_token or not chat_ids:
        return results

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            resp = requests.post(url, data=payload, timeout=8)
            resp_json = resp.json() if resp.headers.get("content-type","").startswith("application/json") else {}
            results[chat_id] = {"ok": resp_json.get("ok", False)}
        except Exception as e:
            results[chat_id] = {"ok": False, "exception": str(e)}
    return results

# --------------------------- YFINANCE DATA ---------------------------
def fetch_intraday_yfinance(symbol, period="1d", interval="5m", max_retries=2):
    for _ in range(max_retries):
        try:
            df = yf.download(symbol, period=period, interval=interval, progress=False, threads=False)
            if df is None or df.empty:
                continue
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(TIMEZONE)
            df = df.reset_index()
            df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
            df.rename(columns={"datetime":"datetime","date":"datetime","adj close":"close"}, inplace=True)
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.sort_values("datetime").dropna(subset=["close"]).reset_index(drop=True)
            return df[["datetime","open","high","low","close","volume"]]
        except Exception as e:
            print(f"yfinance error {symbol}: {e}")
    return None

# --------------------------- INDICATORS ---------------------------
def compute_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].replace(0,np.nan).cumsum()
    df['vwap'] = vwap.fillna(method="ffill").fillna(0)
    return df

def calculate_indicators(df):
    if len(df) < 20:
        return df
    try:
        df['ema20'] = ta.trend.EMAIndicator(df['close'], 20).ema_indicator()
        df['ema50'] = ta.trend.EMAIndicator(df['close'], 50).ema_indicator()
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], 14).rsi()
        macd = ta.trend.MACD(df['close'])
        df['macd_hist'] = macd.macd_diff()
        bb = ta.volatility.BollingerBands(df['close'], 20, 2)
        df['bb_high'], df['bb_low'] = bb.bollinger_hband(), bb.bollinger_lband()
        df['atr'] = ta.volatility.AverageTrueRange(df['high'],df['low'],df['close'],14).average_true_range()
        df['adx'] = ta.trend.ADXIndicator(df['high'],df['low'],df['close'],14).adx()
        df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        df['roc'] = ta.momentum.ROCIndicator(df['close'], 9).roc()
        df = compute_vwap(df)
        df['vol_avg_20'] = df['volume'].rolling(20).mean()
    except Exception as e:
        print("indicator error:", e)
    return df

# --------------------------- SCORING ---------------------------
def score_stock(df):
    if df is None or df.empty: return 0
    latest = df.iloc[-1]
    score = 0

    if latest.get("ema20",0) > latest.get("ema50",0): score += 20
    if latest.get("macd_hist",0) > 0: score += 10
    if 30 < latest.get("rsi",50) < 60: score += 12
    elif latest.get("rsi",0) < 30: score += 8
    elif latest.get("rsi",100) < 75: score += 6
    if latest.get("volume",0) > 1.5 * latest.get("vol_avg_20",1): score += 15
    if latest.get("close",0) > latest.get("vwap",0): score += 10
    if latest.get("adx",0) > 25: score += 10
    return max(0,min(100,int(score)))

def classify_signal(score, df):
    if score >= 75: return "STRONG BUY"
    if score >= 60: return "BUY"
    if score >= 45: return "HOLD"
    return "SELL"

# --------------------------- FUTURE PROJECTION ---------------------------
def compute_future_potential(df, days=10):
    if len(df)<2: return {i+1:0 for i in range(days)}
    avg = df['close'].pct_change().dropna().mean()
    return {i+1: avg*100*(i+1) for i in range(days)}

# --------------------------- WRAPPER ---------------------------
def fetch_and_analyze(symbol, trend_minutes=30, forecast_days=10, interval="5m"):
    df = fetch_intraday_yfinance(symbol, "1d", interval)
    if df is None or df.empty:
        return None
    df = calculate_indicators(df)
    score = score_stock(df)
    signal = classify_signal(score, df)
    fundamentals = {}
    try:
        info = yf.Ticker(symbol).info
        fundamentals = {
            "PE_ratio": info.get("trailingPE"),
            "EPS": info.get("trailingEps"),
            "Market_Cap": info.get("marketCap")
        }
    except: pass
    past_price = df['close'].iloc[-trend_minutes] if len(df)>trend_minutes else df['close'].iloc[0]
    future_potential = (df['close'].iloc[-1]-past_price)/past_price*100 if past_price else 0
    return {
        "symbol": symbol,
        "score": score,
        "signal": signal,
        "current_price": float(df['close'].iloc[-1]),
        "datetime": str(df['datetime'].iloc[-1]),
        "future_potential": future_potential,
        "future_10_days": compute_future_potential(df, forecast_days),
        "df": df,
        "fundamentals": fundamentals
    }
