# utils.py - Nifty50 helper functions
import time
import pandas as pd
import numpy as np
import pytz
import requests
import yfinance as yf
import ta
from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS

IST = pytz.timezone(TIMEZONE)

# --------------------------- TELEGRAM ---------------------------
def send_telegram_message(bot_token, message, chat_ids=None):
    """
    Send message to provided chat_ids or the hardcoded list.
    Returns dict with status per chat.
    """
    results = {}
    if chat_ids is None:
        chat_ids = TELEGRAM_CHAT_IDS
    chat_ids = [str(c) for c in (chat_ids or [])]
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
    """Download yfinance data safely with retries and fallback to daily."""
    for attempt in range(max_retries):
        try:
            df = yf.download(yf_symbol, period=period, interval=interval, progress=False, threads=False)
            if df is None or df.empty:
                # fallback: try longer period with daily interval
                df = yf.download(yf_symbol, period="5d", interval="1d", progress=False, threads=False)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            print(f"[DEBUG] yfinance error {yf_symbol}: {e} (attempt {attempt+1})")
        time.sleep(sleep_between)
    return None

def fetch_intraday_yfinance(symbol, period="1d", interval="5m"):
    """
    Return dataframe with columns datetime, open, high, low, close, volume.
    Handles symbols like M&M properly by removing & and appending .NS
    """
    yf_symbol = symbol.replace("&", "") + ".NS"
    df = safe_yf_download(yf_symbol, period=period, interval=interval)
    if df is None or df.empty:
        return None

    try:
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(TIMEZONE)
    except Exception:
        pass

    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    if 'adj close' in df.columns and 'close' not in df.columns:
        df = df.rename(columns={'adj close': 'close'})
    for col in ["datetime", "open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = np.nan
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values("datetime").dropna(subset=["close"]).reset_index(drop=True)
    return df[["datetime", "open", "high", "low", "close", "volume"]]

# --------------------------- INDICATORS ---------------------------
def calculate_indicators(df):
    """Add basic indicators safely."""
    try:
        if df.shape[0] < 3:
            return df
        df = df.copy()
        if df.shape[0] >= 20:
            try:
                df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
                df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
            except Exception as e:
                print("[DEBUG] EMA error:", e)
        if df.shape[0] >= 14:
            try:
                df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
            except Exception as e:
                print("[DEBUG] RSI error:", e)
        df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    except Exception as e:
        print("[DEBUG] calculate_indicators error:", e)
    return df

# --------------------------- PERCENT CHANGE ---------------------------
def get_percent_change(df):
    """Percent change since first open to latest close."""
    try:
        if df is None or df.empty:
            return 0.0
        first = float(df['close'].iloc[0])
        last = float(df['close'].iloc[-1])
        if first == 0:
            return 0.0
        return ((last - first) / first) * 100.0
    except Exception:
        return 0.0

# --------------------------- FETCH & ANALYZE ---------------------------
def fetch_and_analyze(symbol):
    """Return dict with symbol, percent_change, current_price, df."""
    df = fetch_intraday_yfinance(symbol, period="1d", interval="5m")
    if df is None or df.empty:
        print(f"[DEBUG] fetch_and_analyze: no data for {symbol}")
        return None
    df = calculate_indicators(df)
    pct = get_percent_change(df)
    current_price = float(df['close'].iloc[-1])
    return {"symbol": symbol, "percent_change": pct, "current_price": current_price, "df": df}

# --------------------------- TOP 10 ---------------------------
def get_top10_by_percent(symbols):
    """Return top 10 symbols by percent change."""
    results = []
    for s in symbols:
        try:
            info = fetch_and_analyze(s)
            if info:
                results.append(info)
        except Exception as e:
            print(f"[DEBUG] get_top10_by_percent error for {s}: {e}")
    results.sort(key=lambda x: x.get('percent_change', 0.0), reverse=True)
    return results[:10]

def send_top10_telegram(symbols):
    """Fetch top 10 and send Telegram message."""
    top10 = get_top10_by_percent(symbols)
    if not top10:
        msg = "<b>No Top-10 data available right now (yfinance returned no data)</b>"
        return send_telegram_message(TELEGRAM_BOT_TOKEN, msg)

    message = "<b>🔥 Top 10 Nifty 50 Stocks (by % change) 🔥</b>\n\n"
    for i, s in enumerate(top10, 1):
        pct = s.get('percent_change', 0.0)
        sign = "+" if pct >= 0 else ""
        message += f"{i}. {s['symbol']} | {sign}{pct:.2f}% | ₹{s['current_price']:.2f}\n"
    return send_telegram_message(TELEGRAM_BOT_TOKEN, message)
