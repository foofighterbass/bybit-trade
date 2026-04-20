"""Запускает стратегии параллельно в отдельных потоках."""
import json
import logging
import threading
import time

import config
import exchange
from . import database
from .risk import RiskManager
from strategies import REGISTRY

log = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 300  # логировать "живой" каждые N секунд


class StrategyRunner:
    def __init__(self):
        self._threads: dict[str, threading.Thread] = {}
        self._stops:   dict[str, threading.Event]  = {}
        self._cfgs:    dict[str, dict]              = {}

    def start(self, reset: bool = False, only: str | None = None) -> None:
        for cfg in load_configs():
            if not cfg.get("enabled", True):
                log.info("[%s] отключена (enabled=false)", cfg["id"])
                continue
            if only and cfg["id"] != only:
                continue
            self._launch(cfg, reset)

        if not self._threads:
            log.warning("Нет активных стратегий для запуска. Проверь strategies.json.")
            return

        # watchdog: перезапускает упавшие потоки
        t = threading.Thread(target=self._watchdog, name="watchdog", daemon=True)
        t.start()

    def _launch(self, cfg: dict, reset: bool) -> None:
        sid = cfg["id"]
        cls = REGISTRY.get(cfg["type"])
        if not cls:
            log.error("[%s] Неизвестный тип стратегии: %s", sid, cfg["type"])
            return

        stop = threading.Event()
        self._stops[sid] = stop
        self._cfgs[sid]  = cfg
        t = threading.Thread(
            target=self._loop,
            args=(cls, cfg, reset, stop),
            name=f"strategy-{sid}",
            daemon=True,
        )
        self._threads[sid] = t
        t.start()
        log.info("[%s] Запущена (капитал=%s USDT)", sid, cfg.get("capital_usdt", "—"))

    def _watchdog(self) -> None:
        while True:
            time.sleep(60)
            for sid, t in list(self._threads.items()):
                stop = self._stops.get(sid)
                if stop and stop.is_set():
                    continue  # стратегия остановлена намеренно
                if not t.is_alive():
                    log.error("[watchdog] Поток %s мёртв — перезапускаю", sid)
                    cfg = self._cfgs[sid]
                    cls = REGISTRY.get(cfg["type"])
                    new_stop = threading.Event()
                    self._stops[sid] = new_stop
                    new_t = threading.Thread(
                        target=self._loop,
                        args=(cls, cfg, False, new_stop),
                        name=f"strategy-{sid}",
                        daemon=True,
                    )
                    self._threads[sid] = new_t
                    new_t.start()

    def _loop(self, cls, cfg: dict, reset: bool, stop: threading.Event) -> None:
        sid     = cfg["id"]
        capital = float(cfg.get("capital_usdt", 10_000))
        max_dl  = float(cfg.get("max_daily_loss_pct", config.MAX_DAILY_LOSS_PCT))
        max_dd  = float(cfg.get("max_drawdown_pct",   config.MAX_DRAWDOWN_PCT))

        database.init_wallet(sid, capital)

        strategy = cls(sid, cfg["params"])
        risk     = RiskManager(sid, capital, max_dl, max_dd)

        strategy.setup(reset=reset)

        last_heartbeat = 0.0
        while not stop.is_set():
            try:
                bal_info = exchange.get_account()
                balance  = float(bal_info.get("available", 0))
                equity   = float(bal_info.get("equity", balance))
                database.snapshot_balance(balance, equity)

                if not risk.check():
                    log.error("[%s] Риск-лимит сработал — стратегия остановлена. "
                              "Для возобновления перезапусти бота вручную.", sid)
                    break

                strategy.tick()

                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    vbal = database.get_virtual_balance(sid)
                    log.info("[%s] alive | virtual_balance=%.2f | account=%.2f equity=%.2f",
                             sid, vbal, balance, equity)
                    last_heartbeat = now

            except Exception as exc:
                log.error("[%s] Ошибка: %s", sid, exc, exc_info=True)

            stop.wait(config.POLL_INTERVAL)

        strategy.shutdown()
        log.info("[%s] Остановлена", sid)

    def stop_all(self) -> None:
        for event in self._stops.values():
            event.set()

    def stop_one(self, strategy_id: str) -> bool:
        if strategy_id not in self._stops:
            return False
        self._stops[strategy_id].set()
        return True

    def wait(self) -> None:
        for t in self._threads.values():
            t.join()

    def running_ids(self) -> list[str]:
        return [sid for sid, t in self._threads.items() if t.is_alive()]


def load_configs() -> list[dict]:
    with open("strategies.json", encoding="utf-8") as f:
        return json.load(f)
