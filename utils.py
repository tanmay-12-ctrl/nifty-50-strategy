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

# --------------------------- TELEGRAM ---------------------------
def load_chat_ids():
    """Loads chat IDs from both config file and a JSON file."""
    config_ids = [str(i) for i in (TELEGRAM_CHAT_IDS or [])]
    if os.path.exists(CHAT_IDS_FILE):
        try:
            with open(CHAT_IDS_FILE, "r") as f:
                file_ids = json.load(f)
                file_ids = [str(i) for i in file_ids]
                # Combine and remove duplicates
                return list(dict.fromkeys(config_ids + file_ids))
        except (json.JSONDecodeError, IOError):
            pass  # If file is empty or corrupt, fall back to config
    return config_ids

def save_chat_ids(ids):
    """Saves a list of unique chat IDs to a JSON file."""
    unique_ids = list(dict.fromkeys(str(i) for i in ids))
    with open(CHAT_IDS_FILE, "w") as f:
        json.dump(unique_ids, f, indent=2)

def auto_add_new_chats():
    """Fetches updates from Telegram to find new users who started the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Warning: TELEGRAM_BOT_TOKEN is not set. Cannot auto-add new chats.")
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
                print(f"New chat detected: {chat_id}. Adding to list.")
                chat_ids.append(str(chat_id))
        save_chat_ids(chat_ids)
    except requests.RequestException as e:
        print(f"Telegram API connection failed: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in auto_add_new_chats: {e}")
    return chat_ids

def send_telegram_message(bot_token, message, chat_ids=None):
    """Sends a message to a list of Telegram chat IDs."""
    results = {}
    if chat_ids is None:
        chat_ids = load_chat_ids()

    if not bot_token or not chat_ids:
        print("Error: Bot token or chat IDs are missing. Cannot send message.")
        return results

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            resp = requests.post(url, data=payload, timeout=8)
            resp_json = resp.json()
            results[chat_id] = {"ok": resp_json.get("ok", False), "response": resp_json}
        except Exception as e:
            results[chat_id] = {"ok": False, "exception": str(e)}
    return results


# --------------------------- DATA & ANALYSIS ---------------------------
def fetch_and_analyze(symbol):
    """
    Fetches intraday data for a stock, calculates its daily percentage change,
    and computes a technical score.
    """
    try:
        # 1. Fetch Intraday Data
        df = yf.download(
            symbol,
            period="1d",
            interval="5m",
            progress=False,
            threads=False
        )
        if df.empty:
            return None

        # 2. Fetch Ticker Info for Previous Close
        ticker_info = yf.Ticker(symbol).info
        prev_close = ticker_info.get("previousClose")
        current_price = df['Close'].iloc[-1]

        # 3. Calculate Daily Percentage Change (the key metric)
        day_change_pct = 0.0
        if prev_close and current_price:
            day_change_pct = ((current_price - prev_close) / prev_close) * 100

        # 4. Calculate Technical Score
        df['ema20'] = ta.trend.EMAIndicator(df['Close'], 20).ema_indicator()
        df['rsi'] = ta.momentum.RSIIndicator(df['Close'], 14).rsi()
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['vwap'] = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()

        latest = df.iloc[-1]
        score = 0
        if latest['Close'] > latest['vwap']: score += 40
        if latest['Close'] > latest['ema20']: score += 30
        if 40 < latest['rsi'] < 70: score += 30
        score = int(score)

        signal = "HOLD"
        if score >= 70: signal = "STRONG BUY"
        elif score >= 50: signal = "BUY"


        return {
            "symbol": symbol,
            "current_price": float(current_price),
            "day_change_pct": day_change_pct,
            "score": score,
            "signal": signal,
        }

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None