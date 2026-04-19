"""Риск-менеджер: останавливает бота при превышении лимитов убытка."""
import logging
import database
import config

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        self.peak: float | None = None

    def check(self, balance: float) -> bool:
        """Возвращает False если бота нужно остановить."""
        if self.peak is None:
            self.peak = balance
        self.peak = max(self.peak, balance)

        if self.peak == 0:
            return True

        daily_pnl = database.get_daily_pnl()
        daily_loss_pct = abs(daily_pnl) / self.peak * 100
        if daily_pnl < 0 and daily_loss_pct >= config.MAX_DAILY_LOSS_PCT:
            log.error("СТОП: Дневной убыток %.1f%% > лимита %.0f%%", daily_loss_pct, config.MAX_DAILY_LOSS_PCT)
            return False

        drawdown_pct = (self.peak - balance) / self.peak * 100
        if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
            log.error("СТОП: Просадка %.1f%% > лимита %.0f%%", drawdown_pct, config.MAX_DRAWDOWN_PCT)
            return False

        return True
