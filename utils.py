# utils.py (FULL UPDATED)
import pandas as pd
import numpy as np
import pytz
import requests
import ta
import yfinance as yf
from config import TIMEZONE, TELEGRAM_BOT_TOKEN

IST = pytz.timezone(TIMEZONE)

# --------------------------- TELEGRAM ---------------------------
TELEGRAM_CHAT_IDS = ["1438699528", "5719791363"]  # hardcoded chat IDs

def load_chat_ids():
    # Only return hardcoded IDs
    return [str(i) for i in TELEGRAM_CHAT_IDS]

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

# --------------------------- TOP 10 BY % CHANGE ---------------------------
def get_top10_by_percent(nifty50_symbols):
    stocks_data = []
    for symbol in nifty50_symbols:
        df = fetch_intraday_yfinance(symbol, period="1d", interval="5m")
        if df is None or df.empty: 
            continue
        latest = df.iloc[-1]
        open_price = df['open'].iloc[0]
        percent_change = ((latest['close'] - open_price)/open_price)*100
        stocks_data.append({
            "symbol": symbol,
            "current_price": float(latest['close']),
            "percent_change": percent_change
        })
    top10 = sorted(stocks_data, key=lambda x: x['percent_change'], reverse=True)[:10]
    return top10

def send_top10_telegram(nifty50_symbols):
    top10 = get_top10_by_percent(nifty50_symbols)
    message = "<b>Top 10 Nifty 50 Stocks Today</b>\n\n"
    for i, stock in enumerate(top10, 1):
        sign = "+" if stock['percent_change'] >= 0 else ""
        message += f"{i}. {stock['symbol']} | {sign}{stock['percent_change']:.2f}% | ₹{stock['current_price']}\n"
    send_telegram_message(TELEGRAM_BOT_TOKEN, message)
