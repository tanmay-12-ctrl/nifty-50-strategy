import os
from dotenv import load_dotenv

# Load .env for secrets
load_dotenv()

# DATA PROVIDER
DATA_PROVIDER = "yfinance"

# Broker / API keys (if you use them)
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")
PROVIDER_API_SECRET = os.getenv("PROVIDER_API_SECRET", "")
PROVIDER_ACCESS_TOKEN = os.getenv("PROVIDER_ACCESS_TOKEN", "")

# Telegram
# Loads the token from your .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ✅ FIX: Hardcode your chat IDs directly here for reliability.
TELEGRAM_CHAT_IDS = ["1438699528", "5719791363"]

# Portfolio & money
TOTAL_CAPITAL = 1000000   # ₹10,00,000
STOP_LOSS_PERCENT = 2     # alert if loss >= 2%
PARTIAL_SELL_PERCENT = 25 # partial sell %

# Timezone
TIMEZONE = "Asia/Kolkata"

# NIFTY50 symbols
NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",

    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LTIM",
    "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TCS", "TECHM", "TITAN", "ULTRACEMCO", "WIPRO"
]