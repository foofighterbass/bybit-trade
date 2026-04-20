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
