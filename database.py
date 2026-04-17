"""SQLite: хранение состояния сетки, истории сделок, дневного PnL."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/trades.db")


def init():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL,
                symbol    TEXT NOT NULL,
                side      TEXT NOT NULL,
                qty       REAL NOT NULL,
                price     REAL NOT NULL,
                order_id  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS grid_orders (
                order_id   TEXT PRIMARY KEY,
                symbol     TEXT NOT NULL,
                side       TEXT NOT NULL,
                price      REAL NOT NULL,
                qty        TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                filled_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_pnl (
                date     TEXT PRIMARY KEY,
                realized REAL NOT NULL DEFAULT 0,
                trades   INTEGER NOT NULL DEFAULT 0
            );
        """)


def save_order(order_id: str, symbol: str, side: str, price: float, qty: str):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO grid_orders "
            "(order_id, symbol, side, price, qty, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (order_id, symbol, side, price, qty, "active", _now()),
        )


def mark_filled(order_id: str, pnl: float = 0.0):
    date = _now()[:10]
    with _connect() as conn:
        conn.execute(
            "UPDATE grid_orders SET status='filled', filled_at=? WHERE order_id=?",
            (_now(), order_id),
        )
        conn.execute(
            "INSERT INTO daily_pnl (date, realized, trades) VALUES (?,?,1) "
            "ON CONFLICT(date) DO UPDATE SET realized=realized+?, trades=trades+1",
            (date, pnl, pnl),
        )


def log_trade(symbol: str, side: str, qty: float, price: float, order_id: str):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO trades (ts, symbol, side, qty, price, order_id) VALUES (?,?,?,?,?,?)",
            (_now(), symbol, side, qty, price, order_id),
        )


def load_active_orders(symbol: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM grid_orders WHERE symbol=? AND status='active'", (symbol,)
        ).fetchall()
    return [dict(r) for r in rows]


def cancel_all_orders(symbol: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE grid_orders SET status='cancelled' WHERE symbol=? AND status='active'",
            (symbol,),
        )


def get_daily_pnl(date: str | None = None) -> float:
    d = date or _now()[:10]
    with _connect() as conn:
        row = conn.execute("SELECT realized FROM daily_pnl WHERE date=?", (d,)).fetchone()
    return row["realized"] if row else 0.0


def get_trades(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
