"""PostgreSQL: хранение состояния стратегий, истории сделок, дневного PnL."""
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

import config

log = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


@contextmanager
def _connect():
    conn = psycopg2.connect(config.DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    """Точка входа: запускает все ожидающие миграции."""
    migrate()


def migrate():
    """Применяет новые миграции из папки migrations/ в порядке имён файлов.

    Уже применённые миграции пропускаются — данные не трогаются.
    Каждый новый деплой автоматически подхватывает новые .sql файлы.
    """
    # Сначала создаём таблицу учёта миграций (если ещё нет)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename   TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        log.warning("Папка migrations/ пуста или не найдена: %s", _MIGRATIONS_DIR)
        return

    for path in migration_files:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s", (path.name,)
                )
                if cur.fetchone():
                    continue  # уже применена

                log.info("Применяю миграцию: %s", path.name)
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO schema_migrations (filename, applied_at) VALUES (%s, %s)",
                    (path.name, _now()),
                )


# ── Виртуальные кошельки стратегий ───────────────────────────────────────────

def init_wallet(strategy_id: str, capital: float) -> None:
    """Создаёт кошелёк при первом запуске; при повторных запусках ничего не меняет."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO strategy_wallets (strategy_id, capital_usdt, virtual_balance, updated_at)"
                " VALUES (%s,%s,%s,%s) ON CONFLICT (strategy_id) DO NOTHING",
                (strategy_id, capital, capital, _now()),
            )


def get_virtual_balance(strategy_id: str) -> float:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT virtual_balance FROM strategy_wallets WHERE strategy_id=%s",
                (strategy_id,),
            )
            row = cur.fetchone()
    return float(row["virtual_balance"]) if row else 0.0


def get_wallets_summary() -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT strategy_id, capital_usdt, virtual_balance, updated_at"
                " FROM strategy_wallets ORDER BY strategy_id"
            )
            return [dict(r) for r in cur.fetchall()]


def _apply_pnl(cur, strategy_id: str, pnl: float) -> None:
    """Обновляет daily_pnl и virtual_balance в одной транзакции.

    Счётчик trades инкрементируется только при pnl != 0 (завершённый цикл),
    чтобы Grid-покупки (pnl=0) не искажали статистику.
    """
    date       = _now()[:10]
    trade_incr = 1 if pnl != 0 else 0
    cur.execute(
        "INSERT INTO daily_pnl (date, strategy_id, realized, trades) VALUES (%s,%s,%s,%s)"
        " ON CONFLICT (date, strategy_id) DO UPDATE"
        " SET realized = daily_pnl.realized + EXCLUDED.realized,"
        "     trades   = daily_pnl.trades + EXCLUDED.trades",
        (date, strategy_id, pnl, trade_incr),
    )
    cur.execute(
        "UPDATE strategy_wallets"
        " SET virtual_balance = virtual_balance + %s, updated_at = %s"
        " WHERE strategy_id = %s",
        (pnl, _now(), strategy_id),
    )


# ── Ордера ────────────────────────────────────────────────────────────────────

def save_order(strategy_id: str, order_id: str, symbol: str, side: str, price: float, qty: str):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO grid_orders "
                "(order_id, strategy_id, symbol, side, price, qty, status, created_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (order_id) DO NOTHING",
                (order_id, strategy_id, symbol, side, price, qty, "active", _now()),
            )


def mark_filled(strategy_id: str, order_id: str, pnl: float = 0.0):
    """Для Grid: помечает ордер исполненным и обновляет PnL + виртуальный баланс."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE grid_orders SET status='filled', filled_at=%s WHERE order_id=%s",
                (_now(), order_id),
            )
            _apply_pnl(cur, strategy_id, pnl)


def record_pnl(strategy_id: str, pnl: float) -> None:
    """Для стратегий без ордерной таблицы (DCA и др.): фиксирует PnL сделки."""
    with _connect() as conn:
        with conn.cursor() as cur:
            _apply_pnl(cur, strategy_id, pnl)


def log_trade(strategy_id: str, symbol: str, side: str, qty: float, price: float, order_id: str):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trades (ts, strategy_id, symbol, side, qty, price, order_id)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_now(), strategy_id, symbol, side, qty, price, order_id),
            )


def load_active_orders(strategy_id: str, symbol: str) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM grid_orders"
                " WHERE strategy_id=%s AND symbol=%s AND status='active'",
                (strategy_id, symbol),
            )
            return [dict(r) for r in cur.fetchall()]


def cancel_all_orders(strategy_id: str, symbol: str):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE grid_orders SET status='cancelled'"
                " WHERE strategy_id=%s AND symbol=%s AND status='active'",
                (strategy_id, symbol),
            )


def get_daily_pnl(strategy_id: str, date: str | None = None) -> float:
    d = date or _now()[:10]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT realized FROM daily_pnl WHERE date=%s AND strategy_id=%s",
                (d, strategy_id),
            )
            row = cur.fetchone()
    return row["realized"] if row else 0.0


def get_all_daily_pnl(date: str | None = None) -> list[dict]:
    """PnL всех стратегий за день."""
    d = date or _now()[:10]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT strategy_id, realized, trades FROM daily_pnl WHERE date=%s"
                " ORDER BY strategy_id",
                (d,),
            )
            return [dict(r) for r in cur.fetchall()]


def snapshot_balance(balance: float, equity: float):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO balance_history (ts, balance, equity) VALUES (%s,%s,%s)",
                (_now(), balance, equity),
            )


def get_balance_history(limit: int = 200) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM balance_history ORDER BY id DESC LIMIT %s", (limit,)
            )
            return list(reversed([dict(r) for r in cur.fetchall()]))


def get_trades(limit: int = 20, strategy_id: str | None = None) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            if strategy_id:
                cur.execute(
                    "SELECT * FROM trades WHERE strategy_id=%s ORDER BY id DESC LIMIT %s",
                    (strategy_id, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT %s", (limit,)
                )
            return [dict(r) for r in cur.fetchall()]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
