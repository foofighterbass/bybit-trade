"""
DCA (Dollar Cost Averaging) Strategy
─────────────────────────────────────
Накапливает позицию покупками по расписанию и/или на откатах цены.
Закрывает всю позицию разом при достижении take-profit%.

Параметры strategies.json:
  symbol          — торговая пара, напр. "BTCUSDT"
  order_qty       — объём одной DCA-покупки, напр. "0.001"
  interval_hours  — минимальный интервал между покупками (default: 4)
  dip_pct         — покупать только если цена упала на X% от предыдущей покупки
                    (0 = отключено, покупаем только по времени)
  take_profit_pct — закрыть позицию при росте средней цены на X%
  max_orders      — максимальное число накопленных покупок до take-profit (default: 10)
"""
from __future__ import annotations

import time

import exchange
from core import database
from strategies.base import BaseStrategy


class DCAStrategy(BaseStrategy):
    def __init__(self, strategy_id: str, params: dict):
        super().__init__(strategy_id, params)
        self.symbol          = params["symbol"]
        self.order_qty       = str(params["order_qty"])
        self.interval_hours  = float(params.get("interval_hours", 4))
        self.dip_pct         = float(params.get("dip_pct", 0))
        self.take_profit_pct = float(params["take_profit_pct"])
        self.max_orders      = int(params.get("max_orders", 10))

        self._position_qty:   float = 0.0
        self._avg_price:      float = 0.0
        self._buy_count:      int   = 0
        self._last_buy_price: float = 0.0
        self._last_buy_time:  float = 0.0

    def setup(self, reset: bool = False) -> None:
        if reset:
            self._position_qty   = 0.0
            self._avg_price      = 0.0
            self._buy_count      = 0
            self._last_buy_price = 0.0
            self._last_buy_time  = 0.0
            self.log.info("Состояние DCA сброшено. Открытую позицию закрой вручную если нужно.")
            return

        self._reconstruct_position()
        # При старте сразу не покупаем — ждём полный интервал.
        self._last_buy_time = time.time()

    def tick(self) -> None:
        price = float(exchange.get_ticker(self.symbol)["lastPrice"])

        if self._position_qty > 0 and self._avg_price > 0:
            tp_price = self._avg_price * (1 + self.take_profit_pct / 100)
            if price >= tp_price:
                self._close_position(price)
                return

        if self._buy_count >= self.max_orders:
            self.log.debug("Лимит накоплений (%d) достигнут, ждём take-profit @ %.1f",
                           self.max_orders, self._avg_price * (1 + self.take_profit_pct / 100))
            return

        if self._should_buy(price):
            self._buy(price)

    def shutdown(self) -> None:
        if self._position_qty > 0:
            self.log.warning(
                "DCA остановлена. Открытая позиция: %.4f %s @ avg %.1f — закрой вручную.",
                self._position_qty, self.symbol, self._avg_price,
            )

    # ── внутренняя логика ────────────────────────────────────────────────────

    def _should_buy(self, price: float) -> bool:
        now = time.time()
        interval_ok = (now - self._last_buy_time) >= self.interval_hours * 3600

        if not interval_ok:
            return False

        if self.dip_pct > 0 and self._last_buy_price > 0:
            return price <= self._last_buy_price * (1 - self.dip_pct / 100)

        return True

    def _buy(self, price: float) -> None:
        try:
            result   = exchange.place_order("Buy", self.symbol, self.order_qty, "Market")
            qty      = float(self.order_qty)
            old_cost = self._position_qty * self._avg_price
            self._position_qty += qty
            self._avg_price     = (old_cost + qty * price) / self._position_qty
            self._buy_count    += 1
            self._last_buy_price = price
            self._last_buy_time  = time.time()

            database.log_trade(
                self.id, self.symbol, "Buy", qty, price,
                result.get("orderId", ""),
            )
            self.log.info(
                "DCA Buy #%d | qty=%s @ %.1f | avg=%.1f | pos=%.4f | TP @ %.1f",
                self._buy_count, self.order_qty, price,
                self._avg_price, self._position_qty,
                self._avg_price * (1 + self.take_profit_pct / 100),
            )
        except Exception as exc:
            self.log.error("Ошибка DCA buy: %s", exc)

    def _close_position(self, price: float) -> None:
        qty_str = f"{self._position_qty:.4f}"
        try:
            result = exchange.place_order(
                "Sell", self.symbol, qty_str, "Market", reduce_only=True,
            )
            pnl = self._position_qty * (price - self._avg_price)
            database.log_trade(
                self.id, self.symbol, "Sell", self._position_qty, price,
                result.get("orderId", ""),
            )
            database.record_pnl(self.id, pnl)
            self.log.info(
                "Take-profit! Закрыто %.4f %s @ %.1f | avg=%.1f | pnl=%+.4f USDT",
                self._position_qty, self.symbol, price, self._avg_price, pnl,
            )
            self._position_qty   = 0.0
            self._avg_price      = 0.0
            self._buy_count      = 0
            self._last_buy_price = price
            self._last_buy_time  = time.time()
        except Exception as exc:
            self.log.error("Ошибка закрытия позиции: %s", exc)

    def _reconstruct_position(self) -> None:
        """Восстанавливает состояние позиции из истории сделок в БД."""
        all_trades = database.get_trades(limit=10_000, strategy_id=self.id)
        trades = list(reversed(all_trades))  # get_trades возвращает DESC

        qty  = 0.0
        cost = 0.0
        buys = 0

        for t in trades:
            if t["side"] == "Buy":
                cost += t["qty"] * t["price"]
                qty  += t["qty"]
                buys += 1
                self._last_buy_price = t["price"]
            elif t["side"] == "Sell":
                if qty > 0:
                    avg   = cost / qty
                    cost -= t["qty"] * avg
                qty  -= t["qty"]
                buys  = 0

        self._position_qty = max(0.0, round(qty, 8))
        self._avg_price    = (cost / qty) if qty > 0 else 0.0
        self._buy_count    = buys

        if self._position_qty > 0:
            self.log.info(
                "Восстановлена позиция: %.4f %s @ avg %.1f (%d покупок)",
                self._position_qty, self.symbol, self._avg_price, self._buy_count,
            )
        else:
            self.log.info("Нет открытой позиции, начинаем с нуля.")
