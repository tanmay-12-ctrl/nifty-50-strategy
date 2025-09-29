# main.py
import os
import time
import pytz
import streamlit as st
import pandas as pd
from datetime import datetime

from config import NIFTY50, TIMEZONE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from utils import get_top10_by_percent, send_top10_telegram, send_telegram_message, fetch_and_analyze

IST = pytz.timezone(TIMEZONE)
st.set_page_config(page_title="Nifty50 Analyzer", layout="wide")
st.title("🔥 Nifty50 — Top 10 % Change Analyzer")

# Sidebar
st.sidebar.title("Controls")
if st.sidebar.button("Force refresh"):
    st.experimental_rerun()
auto_refresh = st.sidebar.checkbox("Auto-refresh (every 60s)", value=False)

# Auto-refresh impl (simple)
if auto_refresh:
    last = st.session_state.get("last_refresh", 0.0)
    now = time.time()
    if now - last > 60:
        st.session_state["last_refresh"] = now
        st.experimental_rerun()

st.markdown("### Top 10 by % change (live)")
with st.spinner("Fetching top 10..."):
    top10 = get_top10_by_percent(NIFTY50)

if top10:
    df = pd.DataFrame([{
        "Symbol": t["symbol"],
        "Price": t["current_price"],
        "% Change": round(t["percent_change"], 2)
    } for t in top10])
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data available right now. See logs for details.")

# Telegram tools
st.markdown("---")
st.subheader("Telegram testing / alerts")

st.write("Hardcoded chat IDs:", TELEGRAM_CHAT_IDS)
if st.button("Send test message to Telegram (targets only hardcoded IDs)"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set in environment.")
    else:
        msg = "<b>Test message from Nifty50 Analyzer</b>\nThis is a test — only hardcoded chat IDs will receive this."
        res = send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
        st.json(res)

if st.button("🚀 Send Top 10 (by % change) to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set in environment.")
    else:
        with st.spinner("Sending top10..."):
            res = send_top10_telegram(NIFTY50)
            st.json(res)
            st.success("Sent (see result JSON above)")

st.markdown("---")
st.markdown("**Notes / Troubleshooting:**")
st.markdown("""
- Ensure target users have started your bot (they must send `/start` to the bot).
- If yfinance intraday returns empty (often when market is closed or yfinance is rate-limited), the code falls back to recent daily data.
- Check Streamlit logs (stdout) for `safe_yf_download` and `fetch_and_analyze` printouts to see which symbols failed.
- If many or all tickers return "No data", try increasing the interval to '15m' in `fetch_intraday_yfinance` or run locally during market hours.
""")
