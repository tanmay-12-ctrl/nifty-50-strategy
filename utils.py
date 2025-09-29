# utils.py
import os
import time
import math
import pandas as pd
import numpy as np
import pytz
import requests
import yfinance as yf
import ta
from datetime import datetime, timedelta
from config import TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, CSV_DIR

IST = pytz.timezone(TIMEZONE)
os.makedirs(CSV_DIR, exist_ok=True)

# exposed logs for UI
LAST_FETCH_LOGS = []

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LAST_FETCH_LOGS.append(f"{ts} {msg}")
    # keep last 200
    if len(LAST_FETCH_LOGS) > 200:
        LAST_FETCH_LOGS.pop(0)
    print(ts, msg)

# ---------------- TELEGRAM ----------------
def send_telegram_message(bot_token, message, chat_ids=None):
    results = {}
    if chat_ids is None:
        chat_ids = TELEGRAM_CHAT_IDS
    chat_ids = [str(c) for c in (chat_ids or [])]
    if not bot_token or not chat_ids:
        log("send_telegram_message: missing token or chat ids")
        return results
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        try:
            resp = requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
            try:
                rj = resp.json()
                results[chat_id] = {"ok": bool(rj.get("ok", False)), "resp": rj}
            except Exception:
                results[chat_id] = {"ok": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            results[chat_id] = {"ok": False, "error": str(e)}
    log(f"send_telegram_message results: {results}")
    return results

# ---------------- YFINANCE robust fetch ----------------
def _safe_ticker_history(yf_symbol, interval, period):
    """
    Try different methods to fetch using yf.Ticker().history with exponential backoff.
    Returns DataFrame or None.
    """
    backoff = 0.5
    for attempt in range(4):
        try:
            ticker = yf.Ticker(yf_symbol)
            # history is often more reliable for certain tickers
            df = ticker.history(period=period, interval=interval, actions=False, auto_adjust=False)
            if df is not None and not df.empty:
                return df
            # fallback to download if history empty
            df2 = yf.download(yf_symbol, period=period, interval=interval, progress=False, threads=False)
            if df2 is not None and not df2.empty:
                return df2
        except Exception as e:
            log(f"_safe_ticker_history error {yf_symbol} interval={interval} attempt={attempt+1}: {e}")
        time.sleep(backoff)
        backoff *= 1.8
    return None

def fetch_intraday_with_fallback(symbol, try_intervals=("5m","15m","1h","1d")):
    """
    symbol: plain symbol like "RELIANCE" or "M&M"
    This will:
      - try multiple intervals (5m,15m,1h,1d)
      - normalize columns, ensure 'close' exists
      - save latest CSV per symbol for fallback
      - if all fail, try reading last CSV
    Returns dataframe with lowercase columns and a 'datetime' column
    """
    safe_symbol = symbol.strip()
    yf_symbol = safe_symbol if safe_symbol.endswith(".NS") else f"{safe_symbol}.NS"

    # try intervals in order
    for interval in try_intervals:
        # choose period based on interval
        if interval in ("5m","15m"):
            period = "1d"
        elif interval in ("1h",):
            period = "5d"
        else:
            period = "60d"
        df = _safe_ticker_history(yf_symbol, interval=interval, period=period)
        if df is not None and not df.empty:
            log(f"fetched {yf_symbol} interval={interval} rows={len(df)}")
            # normalize
            df = df.reset_index()
            df.columns = [str(c).lower().strip() for c in df.columns]
            # adj close fix
            if 'adj close' in df.columns and 'close' not in df.columns:
                df = df.rename(columns={'adj close':'close'})
            # ensure required cols
            for col in ["datetime","open","high","low","close","volume"]:
                if col not in df.columns:
                    df[col] = np.nan
            # ensure datetime dtype
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
            df = df.sort_values("datetime").dropna(subset=["close"]).reset_index(drop=True)
            # save CSV for fallback (use symbol no dot)
            safe_filename = yf_symbol.replace("/","_").replace(".","_")
            csvpath = os.path.join(CSV_DIR, f"{safe_filename}_latest.csv")
            try:
                df.to_csv(csvpath, index=False)
            except Exception as e:
                log(f"warning saving csv {csvpath}: {e}")
            return df[["datetime","open","high","low","close","volume"]]
        else:
            log(f"no data for {yf_symbol} at interval {interval}")
            # small delay to be polite
            time.sleep(0.2)

    # if reached here, all intervals failed -> try reading last saved CSV
    safe_filename = yf_symbol.replace("/","_").replace(".","_")
    csvpath = os.path.join(CSV_DIR, f"{safe_filename}_latest.csv")
    if os.path.exists(csvpath):
        try:
            df = pd.read_csv(csvpath)
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
            if 'close' in df.columns:
                df = df.sort_values("datetime").dropna(subset=["close"]).reset_index(drop=True)
                log(f"loaded fallback csv for {yf_symbol} rows={len(df)}")
                return df[["datetime","open","high","low","close","volume"]]
        except Exception as e:
            log(f"failed reading fallback csv {csvpath}: {e}")
    log(f"fetch_intraday_with_fallback: no data for {yf_symbol} after all attempts")
    return None

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    try:
        if df.shape[0] >= 20:
            df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20, fillna=True).ema_indicator()
        if df.shape[0] >= 50:
            df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50, fillna=True).ema_indicator()
        if df.shape[0] >= 14:
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()
        df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    except Exception as e:
        log(f"calculate_indicators error: {e}")
    return df

# ---------------- PERCENT CHANGE ----------------
def get_percent_change(df):
    try:
        if df is None or df.empty or 'close' not in df.columns:
            return 0.0
        first = float(df['close'].iloc[0])
        last = float(df['close'].iloc[-1])
        if first == 0:
            return 0.0
        return ((last - first) / first) * 100.0
    except Exception as e:
        log(f"get_percent_change error: {e}")
        return 0.0

# ---------------- FETCH & ANALYZE ----------------
def fetch_and_analyze(symbol):
    """
    Full fetch + indicators + percent change; returns dict or None
    """
    df = fetch_intraday_with_fallback(symbol, try_intervals=("5m","15m","1h","1d"))
    if df is None or df.empty:
        log(f"fetch_and_analyze: no data for {symbol}")
        return None
    df = calculate_indicators(df)
    if 'close' not in df.columns or df['close'].isnull().all():
        log(f"fetch_and_analyze: close missing for {symbol}")
        return None
    pct = get_percent_change(df)
    current_price = float(df['close'].iloc[-1])
    return {"symbol": symbol, "percent_change": pct, "current_price": current_price, "df": df}

# ---------------- TOP10 & TELEGRAM ----------------
def get_top10_by_percent(symbols):
    results = []
    for i, s in enumerate(symbols):
        # rate-limit a bit every N calls
        if i and i % 8 == 0:
            time.sleep(0.5)
        try:
            info = fetch_and_analyze(s)
            if info:
                results.append(info)
        except Exception as e:
            log(f"get_top10 error {s}: {e}")
    results.sort(key=lambda x: x.get('percent_change', 0.0), reverse=True)
    return results[:10]

def send_top10_telegram(symbols):
    top10 = get_top10_by_percent(symbols)
    if not top10:
        msg = "<b>No Top-10 data available right now (yfinance returned no data)</b>"
        return send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
    message = "<b>🔥 Top 10 Nifty50 Stocks (by % change) 🔥</b>\n\n"
    for i, s in enumerate(top10, 1):
        pct = s.get('percent_change', 0.0)
        sign = "+" if pct >= 0 else ""
        message += f"{i}. {s['symbol']} | {sign}{pct:.2f}% | ₹{s['current_price']:.2f}\n"
    return send_telegram_message(TELEGRAM_BOT_TOKEN, message)

def get_last_fetch_logs(n=200):
    return LAST_FETCH_LOGS[-n:]
