import streamlit as st
import pandas as pd
import pytz
import time
from streamlit_autorefresh import st_autorefresh

from config import NIFTY50, TIMEZONE, TELEGRAM_BOT_TOKEN
from utils import get_top10_by_percent, send_top10_telegram, send_telegram_message

IST = pytz.timezone(TIMEZONE)
st.set_page_config(page_title="Nifty50 Analyzer", layout="wide")
st.title("🔥 Nifty50 — Top 10 % Change Analyzer")

# ---------------- SIDEBAR ----------------
st.sidebar.title("Controls")
if st.sidebar.button("Force refresh"):
    st.experimental_rerun()
auto_refresh = st.sidebar.checkbox("Auto-refresh (every 60s)", value=False)
if auto_refresh:
    _ = st_autorefresh(interval=60*1000, key="top10_autorefresh")

# ---------------- TOP 10 TABLE ----------------
st.markdown("### Top 10 by % change (live)")
with st.spinner("Fetching top 10..."):
    top10 = get_top10_by_percent(NIFTY50)

if top10:
    df = pd.DataFrame([{
        "Symbol": t["symbol"],
        "Price": t["current_price"],
        "% Change": round(t["percent_change"],2)
    } for t in top10])
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data available right now. Check logs.")

# ---------------- TELEGRAM ----------------
st.markdown("---")
st.subheader("Telegram alerts (send only to hardcoded IDs)")

if st.button("Send test message"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set in environment.")
    else:
        msg = "<b>Test message from Nifty50 Analyzer</b>"
        res = send_telegram_message(TELEGRAM_BOT_TOKEN, msg)
        st.json(res)

if st.button("🚀 Send Top 10 to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set in environment.")
    else:
        with st.spinner("Sending top10..."):
            res = send_top10_telegram(NIFTY50)
            st.json(res)
            st.success("Sent successfully")

st.markdown("---")
st.markdown("""
**Notes / Troubleshooting:**
- Ensure target users have started your bot (/start)
- If yfinance intraday returns empty, it falls back to last saved CSV
- Run during market hours for real-time intraday data
""")
