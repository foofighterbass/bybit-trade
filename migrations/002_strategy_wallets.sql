CREATE TABLE IF NOT EXISTS strategy_wallets (
    strategy_id      TEXT PRIMARY KEY,
    capital_usdt     REAL NOT NULL,
    virtual_balance  REAL NOT NULL,
    updated_at       TEXT NOT NULL
);
