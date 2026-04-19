"""
Paper trading: симулирует биржу локально без реальных ордеров.

Режимы ценового фида (PAPER_PRICE_FEED):
  real   — берёт текущую цену с Bybit API (только чтение, безопасно)
  random — генерирует случайное блуждание цены (не нужны API ключи)
"""
from __future__ import annotations

import logging
import math
import random
import threading

import config

log = logging.getLogger(__name__)


# ── Ценовой фид ───────────────────────────────────────────────────────────────

class _RealFeed:
    """Берёт цену с биржи (только GET, никаких ордеров)."""
    def __init__(self):
        from pybit.unified_trading import HTTP
        self._session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
        )

    def get_ticker(self, symbol: str) -> dict:
        items = self._session.get_tickers(category="linear", symbol=symbol)["result"]["list"]
        if not items:
            raise ValueError(f"Тикер {symbol} не найден")
        return items[0]

    def get_price(self, symbol: str) -> float:
        return float(self.get_ticker(symbol)["lastPrice"])


class _RandomFeed:
    """Генерирует случайное блуждание цены — без API ключей."""
    def __init__(self):
        self._prices: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_price(self, symbol: str) -> float:
        with self._lock:
            if symbol not in self._prices:
                self._prices[symbol] = config.PAPER_START_PRICE
                log.info("[PAPER] Стартовая цена %s = %.1f", symbol, self._prices[symbol])
            drift = random.gauss(0, config.PAPER_VOLATILITY / 100)
            self._prices[symbol] *= math.exp(drift)
            return round(self._prices[symbol], 1)

    def get_ticker(self, symbol: str) -> dict:
        price = str(self.get_price(symbol))
        return {
            "symbol": symbol, "lastPrice": price,
            "bid1Price": price, "ask1Price": price,
        }


def _make_feed():
    if config.PAPER_PRICE_FEED == "real":
        log.info("[PAPER] Ценовой фид: реальный Bybit API (только чтение)")
        return _RealFeed()
    log.info("[PAPER] Ценовой фид: случайное блуждание (%.2f%% / тик)", config.PAPER_VOLATILITY)
    return _RandomFeed()


# ── Paper Exchange ─────────────────────────────────────────────────────────────

class PaperExchange:
    def __init__(self):
        self._feed = _make_feed()
        self._orders: dict[str, dict] = {}   # fake_id → order dict
        self._lock = threading.Lock()
        self._counter = 0
        log.info("[PAPER] Бумажная биржа инициализирована | баланс=%.2f USDT", config.PAPER_INITIAL_BALANCE)

    # ── Торговые операции (все фейковые) ──────────────────────────────────────

    def place_order(self, side: str, symbol: str, qty: str,
                    order_type: str = "Market", price: str | None = None,
                    reduce_only: bool = False) -> dict:
        with self._lock:
            self._counter += 1
            oid = f"PAPER-{self._counter:06d}"
            self._orders[oid] = {
                "orderId":   oid,
                "symbol":    symbol,
                "side":      side,
                "qty":       str(qty),
                "price":     str(price) if price else "0",
                "orderType": order_type,
            }
        log.info("[PAPER] Размещён %s %s @ %s qty=%s", side, symbol, price or "market", qty)
        return {"orderId": oid}

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        with self._lock:
            self._orders.pop(order_id, None)
        log.info("[PAPER] Отменён %s", order_id)
        return {"orderId": order_id}

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        # Узнаём текущую цену и симулируем исполнения
        symbols = {symbol} if symbol else {o["symbol"] for o in self._orders.values()}
        for sym in symbols:
            try:
                price = self._feed.get_price(sym)
                self._simulate_fills(sym, price)
            except Exception as exc:
                log.warning("[PAPER] Не удалось получить цену %s: %s", sym, exc)

        with self._lock:
            result = list(self._orders.values())
            if symbol:
                result = [o for o in result if o["symbol"] == symbol]
        return result

    def _simulate_fills(self, symbol: str, current_price: float) -> None:
        with self._lock:
            filled = []
            for oid, o in self._orders.items():
                if o["symbol"] != symbol:
                    continue
                if o["orderType"] == "Market":
                    filled.append(oid)
                elif o["side"] == "Buy"  and current_price <= float(o["price"]):
                    filled.append(oid)
                elif o["side"] == "Sell" and current_price >= float(o["price"]):
                    filled.append(oid)
            for oid in filled:
                o = self._orders.pop(oid)
                log.info("[PAPER] ✓ Исполнен %s %s @ %.1f  (рынок=%.1f)",
                         o["side"], o["symbol"], float(o["price"]), current_price)

    # ── Информация о счёте (симулированная) ───────────────────────────────────

    def get_ticker(self, symbol: str) -> dict:
        return self._feed.get_ticker(symbol)

    def get_account(self) -> dict:
        bal = str(config.PAPER_INITIAL_BALANCE)
        return {
            "account_type": "PAPER",
            "equity":       bal,
            "margin_bal":   bal,
            "available":    bal,
            "perp_upnl":    "0",
            "coins": [{
                "coin":      "USDT",
                "balance":   bal,
                "available": bal,
                "usd_value": bal,
                "pnl":       "0",
            }],
        }

    def get_balance(self, coin: str) -> dict:
        bal = str(config.PAPER_INITIAL_BALANCE)
        return {
            "coin":              coin,
            "wallet_balance":    bal,
            "available_balance": bal,
            "unrealized_pnl":   "0",
        }

    def get_positions(self, symbol: str | None = None) -> list[dict]:
        return []

    def get_wallets_raw(self) -> dict:
        return {"PAPER": [{"balance_raw": f"USDT: {config.PAPER_INITIAL_BALANCE} (симуляция)"}]}
