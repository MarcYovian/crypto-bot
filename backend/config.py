import os
from binance.client import Client
import telebot

# Credentials
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '0'))
BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', 'False').lower() in ('true', '1', 't')

# Trading settings
FIXED_LEVERAGE = 15
MAX_RISK_PERCENT = 0.02
DB_NAME = 'data/trading_bot.db'

# Shared Clients
client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET, requests_params={'timeout': 30})
if not hasattr(client, 'https_proxy'):
    client.https_proxy = None
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
