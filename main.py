# main.py
import streamlit as st
import pandas as pd
import time
from streamlit_autorefresh import st_autorefresh
from config import NIFTY50, TELEGRAM_BOT_TOKEN
from utils import get_top10_by_percent, send_top10_telegram, send_telegram_message, get_last_fetch_logs

st.set_page_config(page_title="Nifty50 Analyzer", layout="wide")
st.title("🔥 Nifty50 — Top 10 % Change Analyzer")

# Sidebar
st.sidebar.title("Controls")
if st.sidebar.button("Force refresh"):
    st.experimental_rerun()

auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=True)
if auto_refresh:
    _ = st_autorefresh(interval=60*1000, key="autorefresh")

# Main: fetch top10
st.markdown("### Top 10 by % change (live)")
with st.spinner("Fetching top 10..."):
    top10 = get_top10_by_percent(NIFTY50)

if top10:
    df = pd.DataFrame([{
        "Symbol": t["symbol"],
        "Price (₹)": round(t["current_price"], 2),
        "% Change": round(t["percent_change"], 2)
    } for t in top10])
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No data available right now. Check logs below.")

# Telegram actions (hardcoded IDs are NOT shown)
st.markdown("---")
st.subheader("Telegram alerts")
if st.button("Send Top 10 to Telegram"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set (set it in Streamlit secrets or .env).")
    else:
        with st.spinner("Sending top10..."):
            res = send_top10_telegram(NIFTY50)
            st.json(res)
            st.success("Sent (to hardcoded chat IDs)")

if st.button("Send test message"):
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN not set.")
    else:
        res = send_telegram_message(TELEGRAM_BOT_TOKEN, "<b>Test message from Nifty50 Analyzer</b>")
        st.json(res)

# Logs / debugging area
st.markdown("---")
st.subheader("Fetch logs (latest)")
logs = get_last_fetch_logs(100)
if logs:
    with st.expander("Show last fetch logs (useful for debugging)"):
        st.text("\n".join(logs[-100:]))
else:
    st.info("No logs yet. Trigger a refresh to produce logs.")

st.markdown("""
**Notes:**  
- This app attempts multiple intervals (5m→15m→1h→1d) and falls back to saved CSVs.  
- If you still see 'No data', run the single-symbol test below and paste output here.  
""")

# Single-symbol quick test (useful for debugging)
st.markdown("---")
st.subheader("Single-symbol quick test (debug)")
sym_input = st.text_input("Symbol (plain name, e.g. RELIANCE or M&M)", value="RELIANCE")
if st.button("Run single-symbol test"):
    st.info(f"Running test for {sym_input} — see logs below")
    from utils import fetch_intraday_with_fallback, fetch_and_analyze
    df = fetch_intraday_with_fallback(sym_input, try_intervals=("5m","15m","1h","1d"))
    if df is None:
        st.error("No data returned by fetch_intraday_with_fallback. Check logs.")
    else:
        st.write(df.tail(10))
        res = fetch_and_analyze(sym_input)
        st.write(res)
