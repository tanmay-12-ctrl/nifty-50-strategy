# main.py - Nifty50 dashboard (parallel fetch + Telegram top-10 % change alerts)
import os
import time
from datetime import datetime
import pytz
import concurrent.futures

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Local imports
from config import NIFTY50, TIMEZONE, TELEGRAM_BOT_TOKEN
from utils import fetch_and_analyze, send_top10_telegram, fetch_intraday_yfinance

# Load .env if present
load_dotenv()

# Streamlit config
st.set_page_config(page_title="Nifty50 — Analyzer", layout="wide")
IST = pytz.timezone(TIMEZONE)

# Sidebar controls
st.sidebar.title("⚙️ Controls")
refresh_now = st.sidebar.button("🔁 Refresh scan now")
auto_refresh = st.sidebar.checkbox("Enable auto-refresh", value=False)
refresh_interval = st.sidebar.number_input(
    "Auto refresh interval (sec)", min_value=10, value=60, step=10
)

if auto_refresh:
    last = st.session_state.get("last_refresh", 0)
    now = time.time()
    if now - last > refresh_interval:
        st.session_state["last_refresh"] = now
        st.experimental_rerun()

st.title("🔥 Nifty50 — Analyzer (Top 10 % Change)")
st.caption("All NIFTY50 tickers scanned in parallel. Data provider: yfinance.")

# Build symbols list
symbols = [s + ".NS" for s in NIFTY50]
total = len(symbols)
today_date = datetime.now(IST).strftime("%Y-%m-%d")

# Progress bar
placeholder_progress = st.empty()
progress_bar = placeholder_progress.progress(0)

# ------------------- Parallel fetch -------------------
results = []
max_workers = min(10, max(4, total // 5))

with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
    futures = {exe.submit(fetch_and_analyze, sym): sym for sym in symbols}
    completed = 0
    for fut in concurrent.futures.as_completed(futures):
        sym = futures[fut]
        completed += 1
        try:
            info = fut.result()
            if info is None:
                st.text(f"No data for {sym} (skipping)")
                continue

            df_stock = info.get("df")
            if df_stock is not None and not df_stock.empty:
                # Save daily CSV
                CSV_DIR = "daily_csv"
                os.makedirs(CSV_DIR, exist_ok=True)
                csv_path = os.path.join(CSV_DIR, f"{sym}_{today_date}.csv")
                df_stock.to_csv(csv_path, index=False)

            results.append({
                "symbol": sym,
                "score": info.get("score", 0),
                "signal": info.get("signal", "N/A"),
                "price": info.get("current_price"),
                "future_potential": info.get("future_potential", 0.0),
                "datetime": info.get("datetime"),
            })
        except Exception as e:
            st.text(f"Error processing {sym}: {e}")
        progress_bar.progress(int(completed * 100 / total))

placeholder_progress.empty()

# ------------------- Build DataFrame -------------------
if results:
    df_res = pd.DataFrame(results)
    df_res["score"] = pd.to_numeric(df_res["score"], errors="coerce").fillna(0).astype(int)
    df_res["price"] = pd.to_numeric(df_res["price"], errors="coerce")
else:
    df_res = pd.DataFrame(columns=["symbol","score","signal","price","future_potential","datetime"])
    st.warning("No valid results — check data provider & utils.py")

# ------------------- Display Table -------------------
st.subheader("Top 10 by Score")
st.dataframe(df_res.sort_values("score", ascending=False).head(10), use_container_width=True)

# ------------------- Telegram Alerts -------------------
st.subheader("📩 Telegram Alerts (Top 10 by % Change)")

if st.button("🚀 Send Top 10 % Change to Telegram"):
    send_top10_telegram(symbols)
    st.success("✅ Top 10 % Change message sent to hardcoded chat IDs!")

# ------------------- Forecast View -------------------
st.subheader("🔮 10-Day Forecast (Top 5 by Score)")
forecast_data = {row["symbol"]: row["future_potential"] for _, row in df_res.head(5).iterrows()}

for sym, potential in forecast_data.items():
    st.markdown(f"**{sym}** — Potential next 10 days: {potential:.2f}%")

# ------------------- Footer -------------------
st.markdown("---")
st.markdown("### Troubleshooting Telegram")
st.markdown("""
- Ensure the bot has been started with `/start` by the target users.
- Only the two hardcoded chat IDs will receive the messages.
- Check Streamlit logs for network or API errors.
""")
