import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# Load .env
load_dotenv()

from config import DATA_PROVIDER, NIFTY50, TOTAL_CAPITAL, STOP_LOSS_PERCENT, PARTIAL_SELL_PERCENT, TIMEZONE, TELEGRAM_BOT_TOKEN
from utils import fetch_and_analyze, send_telegram_message, auto_add_new_chats, load_chat_ids

# Auto-refresh
from streamlit_autorefresh import st_autorefresh

IST = pytz.timezone(TIMEZONE)
st.set_page_config(page_title="Nifty50 Trading Assistant", layout="wide")

# --------------------
# Load / create portfolio file
# --------------------
PORTFOLIO_FILE = "portfolio.json"
if not os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump({}, f)

def load_portfolio():
    with open(PORTFOLIO_FILE, "r") as f:
        return json.load(f)

def save_portfolio(p):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=2)

portfolio = load_portfolio()

# --------------------
# Utility functions
# --------------------
def calculate_used_and_left(portfolio):
    used = 0.0
    for sym, entry in portfolio.items():
        used += entry['entry_price'] * entry['quantity']
    left = TOTAL_CAPITAL - used
    return used, left

used_capital, left_capital = calculate_used_and_left(portfolio)

# --------------------
# Sidebar: manual buy/sell
# --------------------
st.sidebar.title("Manual Buy / Portfolio")
st.sidebar.markdown(f"Total capital: ₹{TOTAL_CAPITAL:,}")
st.sidebar.markdown(f"Used: ₹{used_capital:,.2f}   —   Left: ₹{left_capital:,.2f}")

symbol_choice = st.sidebar.selectbox("Select stock to BUY", NIFTY50)
buy_price = st.sidebar.number_input("Buy price (₹)", min_value=0.0, format="%.2f")
buy_qty = st.sidebar.number_input("Quantity", min_value=0, step=1, value=0)
if st.sidebar.button("Enter Buy"):
    ticker = symbol_choice + ".NS"
    invest = buy_price * buy_qty
    _, left_now = calculate_used_and_left(portfolio)
    if invest > left_now + 1e-6:
        st.sidebar.error("Insufficient capital to buy this quantity at this price.")
    elif buy_qty <= 0:
        st.sidebar.error("Enter quantity > 0")
    else:
        portfolio[ticker] = {
            "entry_price": float(buy_price),
            "quantity": int(buy_qty),
            "datetime": datetime.now(IST).isoformat()
        }
        save_portfolio(portfolio)
        st.sidebar.success(f"Saved buy: {ticker} @ {buy_price} x {buy_qty}")

# Manual sell
st.sidebar.header("Manual Sell / Reduce")
sell_symbol = st.sidebar.selectbox("Symbol to sell (from portfolio)", options=[""] + list(portfolio.keys()))
sell_qty = st.sidebar.number_input("Sell quantity (positive int)", min_value=0, step=1, value=0, key="sell_qty")
sell_price = st.sidebar.number_input("Sell price (₹)", min_value=0.0, format="%.2f", key="sell_price")
if st.sidebar.button("Enter Sell"):
    if sell_symbol == "":
        st.sidebar.error("Choose a symbol")
    elif sell_symbol not in portfolio:
        st.sidebar.error("Symbol not in portfolio")
    elif sell_qty <= 0 or sell_qty > portfolio[sell_symbol]['quantity']:
        st.sidebar.error("Invalid sell quantity")
    else:
        portfolio[sell_symbol]['quantity'] -= sell_qty
        if portfolio[sell_symbol]['quantity'] == 0:
            del portfolio[sell_symbol]
        save_portfolio(portfolio)
        st.sidebar.success(f"Sold {sell_qty} of {sell_symbol} at {sell_price}")

# --------------------
# Auto-refresh
# --------------------
st.sidebar.header("Auto-refresh")
auto_refresh = st.sidebar.checkbox("Enable auto refresh (app updates every interval)")
refresh_interval = st.sidebar.number_input("Interval (seconds)", min_value=5, value=30, step=5)
if auto_refresh:
    count = st_autorefresh(interval=refresh_interval*1000, key="autorefresh")

# --------------------
# Auto-add Telegram chat IDs
# --------------------
TELEGRAM_CHAT_IDS = auto_add_new_chats()

# --------------------
# Main UI
# --------------------
st.title("🔥 Nifty50 Analyzer + 10-Day Forecast + CSV Export 🔥")

col1, col2 = st.columns([2,1])

with col2:
    st.subheader("Portfolio")
    st.write(portfolio)
    used_cap, left_cap = calculate_used_and_left(portfolio)
    st.metric("Used capital (₹)", f"{used_cap:,.2f}")
    st.metric("Available (₹)", f"{left_cap:,.2f}")

with col1:
    st.subheader("Instructions")
    st.markdown("""
    1. App fetches previous day’s data if market closed or live data if open.
    2. Computes indicators, composite score, and generates signals.
    3. Shows 10-day projected % changes per stock.
    4. Generates daily CSV per stock. Download for offline analysis.
    """)

# --------------------
# Analysis loop + CSV export
# --------------------
st.subheader("Live / Historical scan & scoring (all NIFTY50)")
progress = st.progress(0)
results = []
all_data = {}
forecast_data = {}

symbols = [s + ".NS" for s in NIFTY50]
total = len(symbols)
i = 0

today_date = datetime.now(IST).strftime("%Y-%m-%d")
CSV_DIR = "daily_csv"
os.makedirs(CSV_DIR, exist_ok=True)

for sym in symbols:
    i += 1
    progress.progress(int(i*100/total))
    try:
        info = fetch_and_analyze(sym, trend_minutes=30, forecast_days=10)
        if info is None:
            continue

        # store raw df for CSV
        df_stock = info['df']
        all_data[sym] = df_stock
        df_stock.to_csv(f"{CSV_DIR}/{sym}_{today_date}.csv", index=False)

        # store 10-day forecast
        forecast_data[sym] = info.get('future_10_days', {})

        # portfolio calculations
        in_port = sym in portfolio
        entry_price = portfolio[sym]['entry_price'] if in_port else None
        qty = portfolio[sym]['quantity'] if in_port else None
        pl = (info['current_price'] - entry_price) * qty if in_port and entry_price else None

        results.append({
            "symbol": sym,
            "score": info['score'],
            "signal": info['signal'],
            "price": info['current_price'],
            "future_potential": info['future_potential'],
            "datetime": info['datetime'],
            "in_portfolio": in_port,
            "entry_price": entry_price,
            "qty": qty,
            "pl": pl
        })
    except Exception as e:
        print("error analyzing", sym, e)
    time.sleep(0.2)

df_res = pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)

# --------------------
# Send Top 10 Buys to Telegram at 10 AM
# --------------------
current_time = datetime.now(IST)
if current_time.hour == 10 and current_time.minute < 5:  # send between 10:00-10:05
    top_10 = df_res.head(10)
    msg = "🔥 Top 10 Buys Today 🔥\n\n"
    for idx, row in top_10.iterrows():
        msg += f"{idx+1}. {row['symbol']} | Price: ₹{row['price']:.2f} | Score: {row['score']:.2f} | Signal: {row['signal']}\n"
    send_telegram_message(TELEGRAM_BOT_TOKEN, msg, TELEGRAM_CHAT_IDS)

# --------------------
# Display Top 10 Buys on Streamlit
# --------------------
st.subheader("Top priority to BUY (today, by composite score)")
st.table(df_res.head(10)[["symbol","price","score","signal"]])

# --------------------
# 10-Day Forecast display (fixed)
# --------------------
st.subheader("📈 10-Day Forecast (% change) per stock")
for sym, forecast in forecast_data.items():
    st.markdown(f"**{sym}**")
    if forecast:
        days = sorted(forecast.keys())
        forecast_df = pd.DataFrame({
            "Day": [f"Day {d}" for d in days],
            "% Change": [forecast[d] for d in days]
        })
        st.table(forecast_df)
    else:
        st.info("No forecast available")

# --------------------
# CSV download
# --------------------
st.subheader("Download CSV of fetched data")
for sym, df_stock in all_data.items():
    csv_name = f"{sym}_{today_date}.csv"
    csv_data = df_stock.to_csv(index=False).encode('utf-8')
    st.download_button(label=f"Download {csv_name}", data=csv_data, file_name=csv_name, mime='text/csv')

# --------------------
# SELL / Stop-loss alerts
# --------------------
st.subheader("Sell / Stop-loss Alerts for your portfolio")
alerts = []
for sym in list(portfolio.keys()):
    row = df_res[df_res['symbol']==sym]
    if row.empty:
        continue
    row = row.iloc[0]
    entry = portfolio[sym]
    current_price = row['price']
    entry_price = entry['entry_price']
    change_pct = (current_price - entry_price)/entry_price*100

    if row['future_potential'] > 0 and row['signal'] in ["SELL", "STRONG SELL"]:
        continue

    if change_pct <= -STOP_LOSS_PERCENT:
        msg = f"⚠️ STOP-LOSS ALERT: {sym} down {change_pct:.2f}% from entry ₹{entry_price:.2f} -> ₹{current_price:.2f}. Consider selling."
        alerts.append(msg)
        send_telegram_message(TELEGRAM_BOT_TOKEN, msg, TELEGRAM_CHAT_IDS)
    elif row['signal'] in ["STRONG SELL", "SELL"]:
        msg = f"⚠️ SELL RECOMMEND: {sym} signal={row['signal']} score={row['score']} potential={row['future_potential']:.2f}%. Current ₹{current_price:.2f}"
        alerts.append(msg)
        send_telegram_message(TELEGRAM_BOT_TOKEN, msg, TELEGRAM_CHAT_IDS)

if alerts:
    for a in alerts:
        st.warning(a)
else:
    st.success("No immediate sell alerts")

# Footer
st.markdown("---")
st.caption("Data provider: YFinance. CSV per day saved in 'daily_csv' folder.")
