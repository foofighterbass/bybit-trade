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

# ── База данных ───────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bot:botpass@db:5432/botdb")

# ── Риск (дефолты, переопределяются в strategies.json) ───────────────────────
MAX_DAILY_LOSS_PCT = _float("MAX_DAILY_LOSS_PCT", 5)
MAX_DRAWDOWN_PCT   = _float("MAX_DRAWDOWN_PCT",   20)

# ── Runner ────────────────────────────────────────────────────────────────────
POLL_INTERVAL = int(_float("POLL_INTERVAL", 30))
