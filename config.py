import os
from dotenv import load_dotenv

load_dotenv()

# ── API ───────────────────────────────────────────────────────────────────────
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if not API_KEY or not API_SECRET:
    raise EnvironmentError(
        "Не заданы BYBIT_API_KEY / BYBIT_API_SECRET. "
        "Скопируй .env.example → .env и заполни ключи."
    )

# ── Grid стратегия ────────────────────────────────────────────────────────────
GRID_SYMBOL = os.getenv("GRID_SYMBOL", "BTCUSDT")
GRID_LEVELS = int(os.getenv("GRID_LEVELS", "5"))        # ордеров с каждой стороны
GRID_SPACING_PCT = float(os.getenv("GRID_SPACING_PCT", "0.5"))  # % между уровнями
GRID_QTY = os.getenv("GRID_QTY", "0.001")              # объём одного ордера

# ── Риск-менеджмент ───────────────────────────────────────────────────────────
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "5"))    # % дневного убытка
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "20"))       # % общей просадки

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Runner ────────────────────────────────────────────────────────────────────
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))   # секунд между проверками
