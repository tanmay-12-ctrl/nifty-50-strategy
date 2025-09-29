# utils.py (REPLACEMENT / improved)
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
            # normalize to strings
            ids = [str(i) for i in ids]
            cfg_ids = [str(i) for i in (TELEGRAM_CHAT_IDS or [])]
            combined = list(dict.fromkeys(ids + cfg_ids))
            return combined
    return [str(i) for i in (TELEGRAM_CHAT_IDS or [])]

def save_chat_ids(ids):
    ids = [str(i) for i in ids]
    with open(CHAT_IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

def auto_add_new_chats():
    """
    Fetch updates and add chat ids if the bot receives messages.
    Use sparingly (don't call every run).
    """
    if not TELEGRAM_BOT_TOKEN:
        print("No TELEGRAM_BOT_TOKEN configured.")
        return load_chat_ids()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    chat_ids = load_chat_ids()
    try:
        r = requests.get(url, timeout=6).json()
        new_ids = []
        for item in r.get("result", []):
            # some updates do not have 'message' (edited_message, callback_query etc.)
            msg = item.get("message") or item.get("edited_message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            chat_id = str(chat_id)
            if chat_id not in chat_ids:
                chat_ids.append(chat_id)
                new_ids.append(chat_id)
        if new_ids:
            print("New chat IDs auto-added:", new_ids)
            save_chat_ids(chat_ids)
    except Exception as e:
        print("Failed to fetch updates (auto_add_new_chats):", e)
    return chat_ids

def send_telegram_message(bot_token, message, chat_ids=None):
    """
    Send message to each chat id. Return dict of results.
    """
    results = {}
    if chat_ids is None:
        chat_ids = load_chat_ids()
    # coerce to strings
    chat_ids = [str(c) for c in (chat_ids or [])]
    if not bot_token or not chat_ids:
        print("Telegram not configured or no chat ids found.")
        return results

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            resp = requests.post(url, data=payload, timeout=8)
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {"ok": False, "status_code": resp.status_code, "text": resp.text[:200]}
            if resp.status_code != 200 or not resp_json.get("ok", False):
                print(f"Telegram send failed for {chat_id}: status={resp.status_code}, body={resp_json}")
                results[chat_id] = {"ok": False, "status": resp.status_code, "body": resp_json}
            else:
                results[chat_id] = {"ok": True}
        except Exception as e:
            print(f"Telegram send exception for {chat_id}:", e)
            results[chat_id] = {"ok": False, "exception": str(e)}
    return results

# --------------------------- YFINANCE DATA ---------------------------
def fetch_intraday_yfinance(symbol, period="1d", interval="5m", max_retries=2):
    """
    Fetch intraday using yfinance for a single symbol.
    Default interval switched to 5m (less noisy and faster).
    Returns DataFrame with columns: datetime, open, high, low, close, volume
    """
    for attempt in range(max_retries):
        try:
            df = yf.download(tickers=symbol, period=period, interval=interval, progress=False, threads=False)
            if df is None or df.empty:
                # sometimes yfinance returns empty; retry once
                continue
            # ensure tz-aware index
            if df.index.tz is None:
                try:
                    df.index = df.index.tz_localize('UTC').tz_convert(TIMEZONE)
                except Exception:
                    # fallback: assume index already localized
                    pass
            df = df.reset_index()
            # standardize column names (yfinance sometimes uses 'Datetime' or 'Date')
            # attempt to rename common variants
            name_map = {}
            for c in df.columns:
                if c.lower() in ("datetime", "date", "index"):
                    name_map[c] = "datetime"
                elif c.lower() == "open":
                    name_map[c] = "open"
                elif c.lower() == "high":
                    name_map[c] = "high"
                elif c.lower() == "low":
                    name_map[c] = "low"
                elif c.lower() in ("close", "adj close", "adjclose"):
                    name_map[c] = "close"
                elif c.lower() == "volume":
                    name_map[c] = "volume"
            df = df.rename(columns=name_map)
            # keep only the expected columns if present
            expected = ["datetime", "open", "high", "low", "close", "volume"]
            for col in expected:
                if col not in df.columns:
                    df[col] = np.nan
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.sort_values("datetime").reset_index(drop=True)
            # drop rows with no price
            df = df.dropna(subset=['close'])
            return df
        except Exception as e:
            print(f"yfinance fetch error {symbol} attempt {attempt+1}: {e}")
    return None

# --------------------------- INDICATORS ---------------------------
def compute_vwap(df):
    # requires volume non-zero, handle zeros
    tp = (df['high'] + df['low'] + df['close']) / 3
    vol_cum = df['volume'].replace(0, np.nan).cumsum().fillna(method='ffill').fillna(0)
    vwap = (tp * df['volume']).cumsum() / (df['volume'].cumsum().replace(0, np.nan)).fillna(method='ffill').fillna(1)
    df['vwap'] = vwap
    return df

def calculate_indicators(df):
    """
    Add indicator columns to df. Be defensive: ensure numeric dtype, fill small NaNs.
    """
    df = df.copy()
    # enforce numeric types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # require minimum rows to compute indicators
    if len(df) < 20:
        # not enough bars: return df with NAN indicator columns
        for col in ['ema20','ema50','rsi','macd','macd_hist','bb_high','bb_low','atr','adx','obv','roc','stoch_rsi','vwap','vol_avg_20']:
            df[col] = np.nan
        return df

    try:
        df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20, fillna=True).ema_indicator()
        df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50, fillna=True).ema_indicator()
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14, fillna=True).rsi()
        macd = ta.trend.MACD(df['close'], fillna=True)
        df['macd'] = macd.macd()
        df['macd_hist'] = macd.macd_diff()
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2, fillna=True)
        df['bb_high'] = bb.bollinger_hband()
        df['bb_low'] = bb.bollinger_lband()
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14, fillna=True).average_true_range()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14, fillna=True).adx()
        df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume'], fillna=True).on_balance_volume()
        df['roc'] = ta.momentum.ROCIndicator(df['close'], window=9, fillna=True).roc()
        try:
            stochrsi = ta.momentum.StochRSIIndicator(df['close'], window=14, smooth1=3, smooth2=3, fillna=True)
            df['stoch_rsi'] = stochrsi.stochrsi()
        except Exception:
            df['stoch_rsi'] = np.nan
        df = compute_vwap(df)
        df['vol_avg_20'] = df['volume'].rolling(20, min_periods=1).mean()
    except Exception as e:
        # if TA fails, log and return df with NAN indicators
        print("Indicator calc error:", e)
        for col in ['ema20','ema50','rsi','macd','macd_hist','bb_high','bb_low','atr','adx','obv','roc','stoch_rsi','vwap','vol_avg_20']:
            if col not in df.columns:
                df[col] = np.nan
    # final sanity: fill small trailing NaNs using ffill for computation (not to create fake values)
    df[['ema20','ema50','rsi','macd','macd_hist','bb_high','bb_low','atr','adx','obv','roc','stoch_rsi','vwap','vol_avg_20']] = \
        df[['ema20','ema50','rsi','macd','macd_hist','bb_high','bb_low','atr','adx','obv','roc','stoch_rsi','vwap','vol_avg_20']].fillna(method='ffill').fillna(0)
    return df

# --------------------------- SCORING + SIGNAL ---------------------------
def score_stock(df):
    # require sufficient indicator data otherwise return 0
    if df is None or len(df) < 20:
        return 0

    latest = df.iloc[-1]
    score = 0
    try:
        trend_pts = 0
        if latest.get('ema20', np.nan) > latest.get('ema50', np.nan):
            trend_pts += 20
        if latest.get('macd_hist', 0) > 0:
            trend_pts += 10
        score += trend_pts
    except Exception:
        pass

    try:
        mom_pts = 0
        rsi = float(latest.get('rsi', np.nan) or 0)
        roc = float(latest.get('roc', np.nan) or 0)
        stoch = float(latest.get('stoch_rsi', np.nan) or np.nan)
        if 30 <= rsi <= 60:
            mom_pts += 12
        elif rsi < 30:
            mom_pts += 8
        elif rsi > 60 and rsi < 75:
            mom_pts += 6
        if not math.isnan(roc) and roc > 0:
            mom_pts += 5
        if not math.isnan(stoch) and stoch < 0.5:
            mom_pts += 3
        score += mom_pts
    except Exception:
        pass

    try:
        vol_pts = 0
        if latest['volume'] > 1.5 * latest['vol_avg_20']:
            vol_pts = 15
        elif latest['volume'] > 1.1 * latest['vol_avg_20']:
            vol_pts = 8
        score += vol_pts
    except Exception:
        pass

    try:
        if latest['close'] > latest['vwap']:
            score += 10
    except Exception:
        pass

    try:
        if latest['adx'] > 25:
            score += 10
        elif latest['adx'] > 18:
            score += 5
    except Exception:
        pass

    try:
        obv = df['obv']
        if len(obv) >= 21:
            if obv.iloc[-1] > obv.rolling(20).mean().iloc[-1]:
                score += 5
    except Exception:
        pass

    try:
        atr_rel = (latest['atr'] / latest['close']) if latest['close'] and latest['atr'] else 0
        if atr_rel < 0.01:
            score += 5
        elif atr_rel < 0.02:
            score += 3
    except Exception:
        pass

    score = max(0, min(100, int(score)))
    return score

def classify_signal(score, df):
    # avoid crashes if df missing bands / rsi
    latest = df.iloc[-1]
    try:
        if not np.isnan(latest.get('bb_low', np.nan)) and latest['close'] < latest['bb_low']:
            return "STRONG SELL"
        if not np.isnan(latest.get('rsi', np.nan)) and latest['rsi'] > 85:
            return "STRONG SELL"
    except Exception:
        pass

    if score >= 70:
        return "STRONG BUY"
    if score >= 55:
        return "BUY"
    if score >= 40:
        return "HOLD"
    return "SELL"

# --------------------------- 10-DAY FUTURE POTENTIAL ---------------------------
def compute_future_potential(df, days=10):
    latest_price = df['close'].iloc[-1]
    if len(df) < 2:
        return {i+1: 0.0 for i in range(days)}
    # safer projection: use simple mean daily percent change
    changes = df['close'].pct_change().dropna()
    avg = changes.mean() if not changes.empty else 0.0
    future = {}
    cum = 0.0
    for i in range(days):
        cum += avg
        future[i+1] = cum * 100
    return future

# --------------------------- HELPER WRAPPER ---------------------------
def fetch_and_analyze(symbol_yf, trend_minutes=30, forecast_days=10, interval="5m"):
    df = fetch_intraday_yfinance(symbol_yf, period="1d", interval=interval)
    if df is None or df.empty:
        print(f"No data for {symbol_yf}")
        return None

    df = calculate_indicators(df)
    fundamentals = {}
    # minimal fundamentals fetch (avoid heavy info calls)
    try:
        ticker = yf.Ticker(symbol_yf)
        info = ticker.info
        fundamentals = {
            "PE_ratio": info.get("trailingPE", np.nan),
            "EPS": info.get("trailingEps", np.nan),
            "Market_Cap": info.get("marketCap", np.nan),
            "Dividend_Yield": info.get("dividendYield", np.nan),
            "PB_ratio": info.get("priceToBook", np.nan),
            "PEG_ratio": info.get("pegRatio", np.nan),
        }
    except Exception:
        fundamentals = {k: np.nan for k in ["PE_ratio","EPS","Market_Cap","Dividend_Yield","PB_ratio","PEG_ratio"]}

    # add fundamentals as scalar metadata only (do not try to add to every row)
    score = score_stock(df)
    signal = classify_signal(score, df)

    if len(df) > trend_minutes:
        past_price = df['close'].iloc[-trend_minutes]
        future_potential = (df['close'].iloc[-1] - past_price) / past_price * 100 if past_price else 0.0
    else:
        future_potential = 0.0

    future_10_days = compute_future_potential(df, days=forecast_days)

    return {
        "symbol": symbol_yf,
        "score": score,
        "signal": signal,
        "current_price": float(df['close'].iloc[-1]),
        "datetime": str(df['datetime'].iloc[-1]),
        "future_potential": future_potential,
        "future_10_days": future_10_days,
        "df": df,
        "fundamentals": fundamentals
    }
