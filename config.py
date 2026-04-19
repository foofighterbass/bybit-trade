import os
from dotenv import load_dotenv

load_dotenv()

# ── API ───────────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
TESTNET    = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if not API_KEY or not API_SECRET:
    raise EnvironmentError(
        "Не заданы BYBIT_API_KEY / BYBIT_API_SECRET. "
        "Скопируй .env.example → .env и заполни ключи."
    )

# ── Paper trading (локальное тестирование без реальных ордеров) ───────────────
PAPER_TRADING         = os.getenv("PAPER_TRADING", "false").lower() == "true"
PAPER_PRICE_FEED      = os.getenv("PAPER_PRICE_FEED", "real")   # "real" | "random"
PAPER_INITIAL_BALANCE = float(os.getenv("PAPER_INITIAL_BALANCE", "10000"))
PAPER_START_PRICE     = float(os.getenv("PAPER_START_PRICE", "84000"))  # для random фида
PAPER_VOLATILITY      = float(os.getenv("PAPER_VOLATILITY", "0.3"))     # % на тик

# ── База данных ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bot:botpass@db:5432/botdb")

# ── Риск (дефолты, переопределяются в strategies.json) ───────────────────────
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "5"))
MAX_DRAWDOWN_PCT   = float(os.getenv("MAX_DRAWDOWN_PCT", "20"))

# ── Runner ────────────────────────────────────────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
