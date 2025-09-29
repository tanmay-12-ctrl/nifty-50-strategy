import streamlit as st
import pandas as pd
import time
from config import NIFTY50, TELEGRAM_BOT_TOKEN
from utils import get_top10_by_percent, send_top10_telegram, send_telegram_message

st.set_page_config(page_title="Nifty50 Analyzer", layout="wide")
st.title("🔥 Nifty50 — Top 10 % Change Analyzer")

# Sidebar
st.sidebar.title("Controls")
if st.sidebar.button("Force refresh"):
    st.experimental_rerun()
auto_refresh = st.sidebar.checkbox("Auto-refresh every 60s", value=True)

if auto_refresh:
    last = st.session_state.get("last_refresh", 0.0)
    now = time.time()
    if now - last > 60:
        st.session_state["last_refresh"] = now
        st.experimental_rerun()

# Top 10 Table
st.markdown("### Top 10 by % change")
with st.spinner("Fetching data..."):
    top10 = get_top10_by_percent(NIFTY50)

if top10:
    df = pd.DataFrame([{
        "Symbol": t["symbol"],
        "Price": t["current_price"],
        "% Change": round(t["percent_change"], 2)
    } for t in top10])
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data available. Market may be closed.")

# Telegram Alerts
st.markdown("---")
st.subheader("Telegram Alerts (hidden chat IDs)")
if st.button("Send Top 10 to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set in .env")
    else:
        with st.spinner("Sending..."):
            res = send_top10_telegram(NIFTY50)
            st.json(res)
            st.success("Sent to hardcoded chat IDs")
