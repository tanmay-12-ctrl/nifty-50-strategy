# main.py
import time
import streamlit as st
import pandas as pd
from config import NIFTY50, TELEGRAM_BOT_TOKEN
from utils import get_top10_by_percent, send_top10_telegram, send_telegram_message

st.set_page_config(page_title="Nifty50 Analyzer", layout="wide")
st.title("🔥 Nifty50 — Top 10 % Change Analyzer")

# Sidebar controls
st.sidebar.title("Controls")
if st.sidebar.button("Force refresh"):
    st.experimental_rerun()
auto_refresh = st.sidebar.checkbox("Auto-refresh (every 60s)", value=False)
if auto_refresh:
    last = st.session_state.get("last_refresh",0.0)
    now = time.time()
    if now - last > 60:
        st.session_state["last_refresh"] = now
        st.experimental_rerun()

# Display Top 10
st.markdown("### Top 10 NIFTY50 by % change")
with st.spinner("Fetching top 10..."):
    top10 = get_top10_by_percent(NIFTY50)

if top10:
    df = pd.DataFrame([{
        "Symbol": t["symbol"],
        "Price": round(t["current_price"],2),
        "% Change": round(t["percent_change"],2)
    } for t in top10])
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data available right now. Check logs.")

# Telegram alert buttons
st.markdown("---")
st.subheader("Telegram alerts")

if st.button("🚀 Send Top 10 to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set")
    else:
        with st.spinner("Sending top 10..."):
            res = send_top10_telegram(NIFTY50)
            st.json(res)
            st.success("Sent successfully (only hardcoded chat IDs receive it)")

if st.button("Send test message to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set")
    else:
        msg = "<b>Test message from Nifty50 Analyzer</b>"
        res = send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
        st.json(res)

st.markdown("---")
st.markdown("**Notes / Troubleshooting:**")
st.markdown("""
- Only hardcoded chat IDs will receive messages; they are hidden from UI.
- Ensure Telegram bot is started by target users (/start).
- If yfinance returns no data (market closed or rate-limited), previous-day CSV fallback is used.
- Check logs for errors or symbols with no data.
""")
