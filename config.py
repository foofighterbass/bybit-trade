import os
from dotenv import load_dotenv

load_dotenv()


def _float(key: str, default: float) -> float:
    """os.getenv + fallback на default если значение пустое или не число."""
    val = os.getenv(key, "").strip()
    try:
        return float(val) if val else default
    except ValueError:
        return default


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
PAPER_PRICE_FEED      = os.getenv("PAPER_PRICE_FEED", "real")
PAPER_INITIAL_BALANCE = _float("PAPER_INITIAL_BALANCE", 10000)
PAPER_START_PRICE     = _float("PAPER_START_PRICE",     84000)
PAPER_VOLATILITY      = _float("PAPER_VOLATILITY",      0.3)

# ── База данных ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bot:botpass@db:5432/botdb")

# ── Риск (дефолты, переопределяются в strategies.json) ───────────────────────
MAX_DAILY_LOSS_PCT = _float("MAX_DAILY_LOSS_PCT", 5)
MAX_DRAWDOWN_PCT   = _float("MAX_DRAWDOWN_PCT",   20)

# ── Runner ────────────────────────────────────────────────────────────────────
POLL_INTERVAL = int(_float("POLL_INTERVAL", 30))
