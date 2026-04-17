"""Telegram-уведомления."""
import logging
import requests
import config

log = logging.getLogger(__name__)
_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"


def send(text: str) -> None:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            _URL,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        log.warning("Telegram: %s", exc)


def on_start(symbol: str, levels: int, spacing: float):
    mode = "DEMO" if config.TESTNET else "REAL"
    send(f"<b>Бот запущен [{mode}]</b>\n{symbol}  {levels} уровней × {spacing}%")


def on_fill(side: str, symbol: str, price: float, qty: str, pnl: float | None = None):
    icon = "BUY" if side == "Buy" else "SELL"
    pnl_str = f"  pnl={pnl:+.4f}" if pnl is not None else ""
    send(f"{icon}  {symbol} @ {price}  qty={qty}{pnl_str}")


def on_stop(reason: str):
    send(f"<b>Бот остановлен</b>\n{reason}")


def on_error(msg: str):
    send(f"Ошибка: {msg}")
