import os
import time
from datetime import datetime
import pytz
import concurrent.futures
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from config import NIFTY50, TIMEZONE, TELEGRAM_BOT_TOKEN
from utils import fetch_and_analyze, send_telegram_message, auto_add_new_chats, load_chat_ids

# --- PAGE CONFIG ---
st.set_page_config(page_title="Nifty50 — Live Movers", layout="wide")
load_dotenv()
IST = pytz.timezone(TIMEZONE)

# --- SIDEBAR CONTROLS ---
st.sidebar.title("⚙️ Controls")
if st.sidebar.button("🔁 Refresh Now"):
    st.cache_data.clear()

auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh", value=True)
refresh_interval = st.sidebar.slider(
    "Refresh Interval (seconds)", min_value=30, max_value=300, value=60, step=15
)

# --- MAIN PAGE ---
st.title("🚀 Nifty50 — Top Movers by Daily % Change")
st.caption(f"Real-time market data from yfinance. Last updated: {datetime.now(IST).strftime('%I:%M:%S %p')}")

# --- DATA FETCHING & PROCESSING ---
@st.cache_data(ttl=refresh_interval - 5)
def get_all_stock_data(symbols_list):
    results = []
    progress_bar = st.progress(0, text="Scanning Nifty50 stocks...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_symbol = {executor.submit(fetch_and_analyze, sym): sym for sym in symbols_list}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_symbol)):
            try:
                data = future.result()
                if data:
                    results.append(data)
            except Exception as e:
                print(f"Error in future result: {e}")
            finally:
                progress_bar.progress((i + 1) / len(symbols_list))
    progress_bar.empty()
    return results

symbols = [s + ".NS" for s in NIFTY50]
all_results = get_all_stock_data(symbols)

# --- DISPLAY DASHBOARD ---
if not all_results:
    st.error("Could not fetch data for any stocks. Please check your internet connection or try again later.")
else:
    df_res = pd.DataFrame(all_results)

    # --- THIS IS THE KEY DYNAMIC SORTING LOGIC ---
    df_res = df_res.sort_values("day_change_pct", ascending=False).reset_index(drop=True)

    df_display = df_res[[
        "symbol",
        "day_change_pct",
        "current_price",
        "signal",
        "score",
    ]].copy()

    # Formatting for better readability
    df_display["symbol"] = df_display["symbol"].str.replace(".NS", "")
    df_display["day_change_pct"] = df_display["day_change_pct"].map('{:+.2f}%'.format)
    df_display["current_price"] = df_display["current_price"].map('₹{:.2f}'.format)

    st.subheader("📊 Live Market Movers")
    st.dataframe(df_display, use_container_width=True, height=500)

    # --- TELEGRAM ALERTS SECTION ---
    st.subheader("📩 Send Top Movers to Telegram")
    top_k_send = st.slider("Number of stocks to send", 1, 20, 10, key="top_k_slider")
    
    topk_df = df_res.head(int(top_k_send))

    msg_lines = [f"🔥 **Top {top_k_send} NIFTY Movers** 🔥\n"]
    for i, row in topk_df.iterrows():
        emoji = "🟢" if row['day_change_pct'] >= 0 else "🔴"
        symbol_name = row['symbol'].replace(".NS", "")
        change_str = f"{row['day_change_pct']:+.2f}%"
        price_str = f"₹{row['current_price']:.2f}"
        msg_lines.append(
            f"<b>{i+1}. {symbol_name}</b> {emoji} {change_str} | Price: {price_str} | Signal: {row['signal']}"
        )
    
    preview_msg = "\n".join(msg_lines)
    st.text_area("Message Preview", value=preview_msg, height=250, key="msg_preview")

    if st.button("🚀 Send to Telegram Now"):
        with st.spinner("Sending..."):
            chat_ids = load_chat_ids()
            if not chat_ids:
                st.error("No chat IDs found! Hardcode them in config.py or have users /start the bot.")
            elif not TELEGRAM_BOT_TOKEN:
                st.error("TELEGRAM_BOT_TOKEN is not set in your environment secrets!")
            else:
                send_results = send_telegram_message(TELEGRAM_BOT_TOKEN, preview_msg, chat_ids)
                ok_count = sum(1 for r in send_results.values() if r.get("ok"))
                if ok_count > 0:
                    st.success(f"✅ Message sent successfully to {ok_count} chat(s).")
                if len(send_results) - ok_count > 0:
                    st.error(f"❌ Failed to send to {len(send_results) - ok_count} chat(s). See details below.")
                    st.json(send_results) # Show detailed error response

# --- AUTO-REFRESH LOGIC ---
if auto_refresh:
    time.sleep(refresh_interval)
    st.experimental_rerun()