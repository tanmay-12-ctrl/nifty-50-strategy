# config.py

# DATA PROVIDER:
# 'yfinance' - no KYC, easy, near-real-time (may be delayed a bit)
# 'broker'    - placeholder for Zerodha/Upstox/Fyers mode (requires broker account + keys)
DATA_PROVIDER = "yfinance"

# If you later use Finnhub/AlphaVantage/broker, put keys here
PROVIDER_API_KEY = ""
PROVIDER_API_SECRET = ""
PROVIDER_ACCESS_TOKEN = ""

# Telegram (for alerts)
TELEGRAM_BOT_TOKEN = "8391435817:AAE6e3PjpdHAu9BVvjVoXSn5iZfM_xpwNvs"
TELEGRAM_CHAT_IDS = ["1438699528", "FRIEND_CHAT_ID"]


# Portfolio & money
TOTAL_CAPITAL = 1000000   # ₹10,00,000
STOP_LOSS_PERCENT = 2     # e.g., alert if loss >= 2%
PARTIAL_SELL_PERCENT = 25 # recommended partial sell percentage

# Timezone
TIMEZONE = "Asia/Kolkata"

# NIFTY50 symbols (as on 28-Mar-2025). For yfinance we append .NS automatically in code.
NIFTY50 = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO","BAJFINANCE",
    "BAJAJFINSV","BEL","BHARTIARTL","CIPLA","COALINDIA","DRREDDY","EICHERMOT","ETERNAL",
    "GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR",
    "ICICIBANK","INDUSINDBK","INFY","ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT","M&M",
    "MARUTI","NESTLEIND","NTPC","ONGC","POWERGRID","RELIANCE","SBILIFE","SHRIRAMFIN",
    "SBIN","SUNPHARMA","TCS","TATACONSUM","TATAMOTORS","TATASTEEL","TECHM","TITAN",
    "TRENT","ULTRACEMCO","WIPRO"
]
