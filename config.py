# config.py
import os
from dotenv import load_dotenv

# Load .env for secrets
load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Hardcoded chat IDs for sending alerts (not shown in UI)
TELEGRAM_CHAT_IDS = ["1438699528", "5719791363"]

# Timezone
TIMEZONE = "Asia/Kolkata"

# Portfolio / capital (optional)
TOTAL_CAPITAL = 1000000
STOP_LOSS_PERCENT = 2
PARTIAL_SELL_PERCENT = 25

# NIFTY50 symbols
NIFTY50 = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK",
    "BAJAJ-AUTO","BAJAJFINSV","BAJFINANCE","BHARTIARTL","BPCL",
    "BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY",
    "EICHERMOT","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE",
    "HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK",
    "INFY","ITC","JSWSTEEL","KOTAKBANK","LTIM",
    "LT","M&M","MARUTI","NESTLEIND","NTPC",
    "ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN",
    "SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL",
    "TCS","TECHM","TITAN","ULTRACEMCO","WIPRO"
]

# CSV folder for storing fetched data
CSV_DIR = "daily_csv"
