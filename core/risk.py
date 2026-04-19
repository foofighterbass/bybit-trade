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

    def check(self, balance: float) -> bool:
        """Возвращает False если стратегию нужно остановить."""
        if self.peak is None:
            self.peak = balance
        self.peak = max(self.peak, balance)

        daily_pnl = database.get_daily_pnl(self.strategy_id)
        if daily_pnl < 0 and abs(daily_pnl) / self.capital * 100 >= self.max_daily_loss_pct:
            log.error("[%s] СТОП: Дневной убыток %.4f USDT >= %.1f%% от капитала %.0f USDT",
                      self.strategy_id, abs(daily_pnl), self.max_daily_loss_pct, self.capital)
            return False

        if self.peak > 0:
            drawdown_pct = (self.peak - balance) / self.peak * 100
            if drawdown_pct >= self.max_drawdown_pct:
                log.error("[%s] СТОП: Просадка счёта %.1f%% >= лимита %.0f%%",
                          self.strategy_id, drawdown_pct, self.max_drawdown_pct)
                return False

        return True
