# config.py
import os
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = "Asia/Kolkata"

# NIFTY50 symbols (plain names; utils will handle .NS)
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

# Telegram token (in Streamlit Cloud use secrets; locally use .env)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Hardcoded chat IDs (used only for sending; NOT shown in UI)
TELEGRAM_CHAT_IDS = ["1438699528", "5719791363"]

# CSV folder
CSV_DIR = "daily_csv"
os.makedirs(CSV_DIR, exist_ok=True)
