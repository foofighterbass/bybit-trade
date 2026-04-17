"""
Grid Trading Strategy
─────────────────────
Ставит лимитные ордера выше и ниже текущей цены.
Когда BUY исполняется → ставит SELL на spacing% выше (и наоборот).
Прибыль за цикл = qty × price × spacing%
"""
from __future__ import annotations
import logging
import exchange
import database
import telegram

log = logging.getLogger(__name__)


class GridStrategy:
    def __init__(self, symbol: str, levels: int, spacing_pct: float, qty: str):
        self.symbol = symbol
        self.levels = levels
        self.spacing = spacing_pct / 100
        self.qty = qty
        self._orders: dict[str, dict] = {}  # order_id → {price, side}

    def setup(self, reset: bool = False) -> None:
        if reset:
            self._cancel_all()
            database.cancel_all_orders(self.symbol)
            self._orders = {}

        saved = database.load_active_orders(self.symbol)
        if saved and not reset:
            log.info("Восстановлено %d ордеров из БД", len(saved))
            self._orders = {r["order_id"]: {"price": r["price"], "side": r["side"]} for r in saved}
            return

        center = float(exchange.get_ticker(self.symbol)["lastPrice"])
        log.info("Инициализация сетки | %s | центр=%.1f | уровней=%d | шаг=%.2f%%",
                 self.symbol, center, self.levels, self.spacing * 100)

        for i in range(1, self.levels + 1):
            self._place("Buy",  round(center * (1 - i * self.spacing), 1))
            self._place("Sell", round(center * (1 + i * self.spacing), 1))

        telegram.on_start(self.symbol, self.levels, self.spacing * 100)

    def tick(self) -> None:
        open_ids = {o["orderId"] for o in exchange.get_open_orders(self.symbol)}
        filled = [(oid, info) for oid, info in list(self._orders.items()) if oid not in open_ids]

        for order_id, info in filled:
            price, side = info["price"], info["side"]
            pnl = float(self.qty) * price * self.spacing if side == "Sell" else None

            log.info("Исполнен %s @ %.1f%s", side, price, f"  pnl={pnl:+.4f}" if pnl else "")
            database.mark_filled(order_id, pnl or 0)
            database.log_trade(self.symbol, side, float(self.qty), price, order_id)
            telegram.on_fill(side, self.symbol, price, self.qty, pnl)

            counter_side = "Sell" if side == "Buy" else "Buy"
            counter_price = round(price * (1 + self.spacing if side == "Buy" else 1 - self.spacing), 1)
            self._place(counter_side, counter_price)
            del self._orders[order_id]

    def shutdown(self) -> None:
        log.info("Отмена всех ордеров...")
        self._cancel_all()
        database.cancel_all_orders(self.symbol)
        self._orders.clear()

    def _place(self, side: str, price: float) -> None:
        try:
            result = exchange.place_order(side, self.symbol, self.qty, "Limit", str(price))
            oid = result["orderId"]
            self._orders[oid] = {"price": price, "side": side}
            database.save_order(oid, self.symbol, side, price, self.qty)
            log.debug("Размещён %s @ %.1f", side, price)
        except Exception as exc:
            log.error("Ошибка размещения %s @ %.1f: %s", side, price, exc)
            telegram.on_error(f"{side} @ {price}: {exc}")

    def _cancel_all(self) -> None:
        for o in exchange.get_open_orders(self.symbol):
            try:
                exchange.cancel_order(self.symbol, o["orderId"])
            except Exception:
                pass
