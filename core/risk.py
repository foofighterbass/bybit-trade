"""Риск-менеджер: останавливает стратегию при превышении лимитов убытка."""
import logging
from . import database

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, strategy_id: str, capital_usdt: float,
                 max_daily_loss_pct: float, max_drawdown_pct: float):
        self.strategy_id        = strategy_id
        self.capital            = capital_usdt
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct   = max_drawdown_pct
        self.peak: float | None = None

    def check(self) -> bool:
        """Возвращает False если стратегию нужно остановить."""
        vbal = database.get_virtual_balance(self.strategy_id)

        if self.peak is None:
            self.peak = vbal
        self.peak = max(self.peak, vbal)

        daily_pnl     = database.get_daily_pnl(self.strategy_id)
        daily_used_pct = abs(daily_pnl) / self.capital * 100 if daily_pnl < 0 else 0.0
        drawdown_pct   = (self.peak - vbal) / self.peak * 100 if self.peak > 0 else 0.0

        if daily_used_pct >= self.max_daily_loss_pct:
            log.error(
                "[%s] СТОП — дневной убыток: %.4f USDT (%.1f%% из %.1f%% лимита) | "
                "virtual_balance=%.2f",
                self.strategy_id, abs(daily_pnl), daily_used_pct,
                self.max_daily_loss_pct, vbal,
            )
            return False

        if drawdown_pct >= self.max_drawdown_pct:
            log.error(
                "[%s] СТОП — просадка: %.1f%% из %.1f%% лимита "
                "(пик=%.2f → текущий=%.2f USDT)",
                self.strategy_id, drawdown_pct, self.max_drawdown_pct,
                self.peak, vbal,
            )
            return False

        # Предупреждение при приближении к лимитам (порог 75%)
        if daily_used_pct >= self.max_daily_loss_pct * 0.75:
            log.warning(
                "[%s] Внимание: дневной убыток %.1f%% — приближается к лимиту %.1f%%",
                self.strategy_id, daily_used_pct, self.max_daily_loss_pct,
            )
        if drawdown_pct >= self.max_drawdown_pct * 0.75:
            log.warning(
                "[%s] Внимание: просадка %.1f%% — приближается к лимиту %.1f%%",
                self.strategy_id, drawdown_pct, self.max_drawdown_pct,
            )

        return True

    def metrics(self) -> dict:
        """Текущие метрики риска для heartbeat."""
        vbal       = database.get_virtual_balance(self.strategy_id)
        daily_pnl  = database.get_daily_pnl(self.strategy_id)
        daily_used = abs(daily_pnl) / self.capital * 100 if daily_pnl < 0 else 0.0
        drawdown   = (self.peak - vbal) / self.peak * 100 if (self.peak or 0) > 0 else 0.0
        return {
            "virtual_balance": vbal,
            "daily_pnl":       daily_pnl,
            "daily_used_pct":  daily_used,
            "drawdown_pct":    drawdown,
        }
