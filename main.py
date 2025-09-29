# main.py - Nifty50 dashboard (parallel fetch + Telegram top-10 alerts)
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
from utils import fetch_and_analyze, send_telegram_message, auto_add_new_chats, load_chat_ids

# Load .env if present
load_dotenv()

# Streamlit config
st.set_page_config(page_title="Nifty50 — Analyzer", layout="wide")
IST = pytz.timezone(TIMEZONE)

# Ensure CSV dir exists
CSV_DIR = "daily_csv"
os.makedirs(CSV_DIR, exist_ok=True)

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

st.title("🔥 Nifty50 — Analyzer (Top-priority by score)")
st.caption("All NIFTY50 tickers scanned in parallel. Data provider: yfinance.")

# Auto-add chats
with st.expander("Telegram Chat IDs"):
    try:
        autolist = auto_add_new_chats()
        st.write("Known chat IDs (from file + config):", autolist)
    except Exception as e:
        st.write("Auto-add failed:", str(e))

# User controls
top_k_display = st.number_input("Show top K (table)", 5, 50, 50, step=5)
top_k_send = st.number_input("Send top K to Telegram", 1, 10, 10, step=1)

# Cached fetch
@st.cache_data(ttl=60)
def cached_fetch(symbol):
    return fetch_and_analyze(symbol, trend_minutes=30, forecast_days=10, interval="5m")

# Build list
symbols = [s + ".NS" for s in NIFTY50]
total = len(symbols)
today_date = datetime.now(IST).strftime("%Y-%m-%d")

# Progress bar
placeholder_progress = st.empty()
progress_bar = placeholder_progress.progress(0)

results = []
all_data = {}
forecast_data = {}

# ThreadPool for parallel fetch
max_workers = min(10, max(4, total // 5))
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
    futures = {exe.submit(cached_fetch, sym): sym for sym in symbols}
    completed = 0
    for fut in concurrent.futures.as_completed(futures):
        sym = futures[fut]
        completed += 1
        try:
            info = fut.result()
            if info is None:
                st.text(f"No data for {sym} (skipping)")
            else:
                df_stock = info.get("df")
                if df_stock is not None and not df_stock.empty:
                    csv_path = os.path.join(CSV_DIR, f"{sym}_{today_date}.csv")
                    df_stock.to_csv(csv_path, index=False)

                all_data[sym] = df_stock
                forecast_data[sym] = info.get("future_10_days", {})

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

# Build dataframe
if results:
    df_res = pd.DataFrame(results)
    df_res["score"] = pd.to_numeric(df_res["score"], errors="coerce").fillna(0).astype(int)
    df_res["price"] = pd.to_numeric(df_res["price"], errors="coerce")
    df_res = df_res.sort_values("score", ascending=False).reset_index(drop=True)
else:
    df_res = pd.DataFrame(columns=["symbol","score","signal","price","future_potential","datetime"])
    st.warning("No valid results — check data provider & utils.py")

# Show table
st.subheader(f"Top {top_k_display} by score")
if not df_res.empty:
    st.dataframe(df_res.head(top_k_display), use_container_width=True)
else:
    st.info("No data to show")

# Quick stats
with st.expander("Top 10 quick stats"):
    st.table(df_res.head(10)[["symbol","price","score","signal"]])

# Telegram block
st.subheader("📩 Telegram Alerts")
topk_df = df_res.head(int(top_k_send))

if topk_df.empty:
    st.info("No results to send.")
else:
    msg_lines = [f"🔥 Top {top_k_send} NIFTY Stocks 🔥\n"]
    for i, row in topk_df.iterrows():
        price_str = f"₹{row['price']:.2f}" if pd.notna(row['price']) else "NA"
        msg_lines.append(
            f"{i+1}. {row['symbol']} | Price: {price_str} | Score: {row['score']} | Signal: {row['signal']}"
        )
    preview_msg = "\n".join(msg_lines)

    st.text_area("Preview message", value=preview_msg, height=220, key="preview_msg_area")

    if st.button("🚀 Send to Telegram"):
        chat_ids = load_chat_ids()
        if not chat_ids:
            st.error("No chat IDs found. Ensure chat_ids.json exists or that the bot received /start.")
        elif not TELEGRAM_BOT_TOKEN:
            st.error("Missing TELEGRAM_BOT_TOKEN.")
        else:
            msg_to_send = st.session_state.get("preview_msg_area", preview_msg)
            send_results = send_telegram_message(TELEGRAM_BOT_TOKEN, msg_to_send, chat_ids)
            st.json(send_results)

            oks = [c for c,r in send_results.items() if r.get("ok")]
            fails = [c for c,r in send_results.items() if not r.get("ok")]
            if oks:
                st.success(f"✅ Sent to {len(oks)} chat(s).")
            if fails:
                st.error(f"❌ Failed for {len(fails)} chat(s). See details above.")

# Forecast view
st.subheader("🔮 10-Day Forecast (Top 5 symbols)")
for sym in df_res.head(5)["symbol"]:
    forecast = forecast_data.get(sym, {})
    st.markdown(f"**{sym}**")
    if forecast:
        rows = [{"Day": f"Day {k}", "% Change": f"{v:.2f}%"} for k,v in sorted(forecast.items())]
        st.table(pd.DataFrame(rows))
    else:
        st.write("No forecast available")

# Footer
st.markdown("---")
st.markdown("### Troubleshooting Telegram")
st.markdown("""
- Start the bot with `/start` inside Telegram.  
- Check `send_results` JSON above for errors.  
- If `ok: true` but no notification, check the correct chat ID and unmute the bot in Telegram.  
""")
