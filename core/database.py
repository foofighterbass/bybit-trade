"""PostgreSQL: хранение состояния стратегий, истории сделок, дневного PnL."""
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

import config


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
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          SERIAL PRIMARY KEY,
                    ts          TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    side        TEXT NOT NULL,
                    qty         REAL NOT NULL,
                    price       REAL NOT NULL,
                    order_id    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS grid_orders (
                    order_id    TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    side        TEXT NOT NULL,
                    price       REAL NOT NULL,
                    qty         TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'active',
                    created_at  TEXT NOT NULL,
                    filled_at   TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_pnl (
                    date        TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    realized    REAL NOT NULL DEFAULT 0,
                    trades      INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (date, strategy_id)
                );

                CREATE TABLE IF NOT EXISTS balance_history (
                    id      SERIAL PRIMARY KEY,
                    ts      TEXT NOT NULL,
                    balance REAL NOT NULL,
                    equity  REAL NOT NULL
                );
            """)


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
    date = _now()[:10]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE grid_orders SET status='filled', filled_at=%s WHERE order_id=%s",
                (_now(), order_id),
            )
            cur.execute(
                "INSERT INTO daily_pnl (date, strategy_id, realized, trades) VALUES (%s,%s,%s,1)"
                " ON CONFLICT (date, strategy_id) DO UPDATE"
                " SET realized = daily_pnl.realized + EXCLUDED.realized,"
                "     trades   = daily_pnl.trades + 1",
                (date, strategy_id, pnl),
            )


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
