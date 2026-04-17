"""Риск-менеджер: останавливает бота при превышении лимитов убытка."""
import logging
import database
import telegram
import config

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        self._peak: float | None = None

    def check(self, balance: float) -> bool:
        """Возвращает False если бота нужно остановить."""
        if self._peak is None:
            self._peak = balance
        self._peak = max(self._peak, balance)

        if self._peak == 0:
            return True

        daily_pnl = database.get_daily_pnl()
        daily_loss_pct = abs(daily_pnl) / self._peak * 100
        if daily_pnl < 0 and daily_loss_pct >= config.MAX_DAILY_LOSS_PCT:
            reason = f"Дневной убыток {daily_loss_pct:.1f}% > лимита {config.MAX_DAILY_LOSS_PCT}%"
            log.error("СТОП: %s", reason)
            telegram.on_stop(reason)
            return False

        drawdown_pct = (self._peak - balance) / self._peak * 100
        if drawdown_pct >= config.MAX_DRAWDOWN_PCT:
            reason = f"Просадка {drawdown_pct:.1f}% > лимита {config.MAX_DRAWDOWN_PCT}%"
            log.error("СТОП: %s", reason)
            telegram.on_stop(reason)
            return False

        return True
