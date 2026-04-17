#!/usr/bin/env python3
"""
Точка входа.

  python bot.py start          # запустить автобота (восстановить состояние)
  python bot.py start --reset  # сбросить сетку и начать заново
  python bot.py status         # активные ордера и PnL

  python bot.py price BTCUSDT
  python bot.py balance
  python bot.py positions
  python bot.py orders
  python bot.py buy  BTCUSDT 0.001 [--type limit --price 60000]
  python bot.py sell BTCUSDT 0.001 [--type limit --price 65000]
  python bot.py cancel BTCUSDT <order_id>
"""
import logging
import signal
import sys
import time

import click
from tabulate import tabulate

import config
import database
import exchange
import telegram
from grid import GridStrategy
from risk import RiskManager

log = logging.getLogger(__name__)


# ── Автобот ───────────────────────────────────────────────────────────────────

@click.group()
def cli():
    pass


@cli.command()
@click.option("--reset", is_flag=True, default=False, help="Пересобрать сетку с нуля")
def start(reset: bool):
    """Запустить Grid-бота."""
    _setup_logging()
    database.init()

    log.info("Старт | %s | testnet=%s | levels=%d | spacing=%.2f%% | qty=%s",
             config.GRID_SYMBOL, config.TESTNET, config.GRID_LEVELS,
             config.GRID_SPACING_PCT, config.GRID_QTY)

    strategy = GridStrategy(config.GRID_SYMBOL, config.GRID_LEVELS,
                            config.GRID_SPACING_PCT, config.GRID_QTY)
    risk = RiskManager()
    running = True

    def on_signal(*_):
        nonlocal running
        log.info("Остановка...")
        telegram.on_stop("Ручная остановка")
        running = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    strategy.setup(reset=reset)

    while running:
        try:
            balance = float(exchange.get_balance("USDT").get("available_balance", 0))
            if not risk.check(balance):
                running = False
                break
            strategy.tick()
        except Exception as exc:
            log.error("Ошибка: %s", exc, exc_info=True)
            telegram.on_error(str(exc))
        time.sleep(config.POLL_INTERVAL)

    strategy.shutdown()
    log.info("Бот остановлен.")


@cli.command()
def status():
    """Активные ордера и дневной PnL."""
    database.init()
    orders = database.load_active_orders(config.GRID_SYMBOL)
    daily = database.get_daily_pnl()
    bal = exchange.get_balance("USDT")

    click.echo(f"\nПара:        {config.GRID_SYMBOL}")
    click.echo(f"Режим:       {'DEMO' if config.TESTNET else 'REAL'}")
    click.echo(f"Баланс:      {bal.get('available_balance', '?')} USDT")
    click.echo(f"Дневной PnL: {daily:+.4f} USDT\n")

    if orders:
        rows = [[o["side"], o["price"], o["qty"], o["created_at"][:19]] for o in orders]
        click.echo(tabulate(rows, headers=["Сторона", "Цена", "Объём", "Создан"]))
    else:
        click.echo("Активных ордеров нет.")
    click.echo()


# ── Информация о счёте ───────────────────────────────────────────────────────

@cli.command()
def wallets():
    """Диагностика: показать баланс во всех типах кошельков (UNIFIED/CONTRACT/SPOT)."""
    raw = exchange.get_wallets_raw()
    for account_type, data in raw.items():
        click.echo(f"\n── {account_type} ──")
        if not data:
            click.echo("  пусто")
            continue
        for acc in data:
            if "error" in acc:
                click.echo(f"  ошибка: {acc['error']}")
                continue
            if "balance_raw" in acc:
                click.echo(f"  {acc['balance_raw']}")
                continue
            coins = [c for c in acc.get("coin", []) if float(c.get("walletBalance", 0)) != 0]
            if not coins:
                click.echo("  баланс: 0")
            for c in coins:
                available = c.get("availableToWithdraw") or c.get("equity") or c["walletBalance"]
                click.echo(f"  {c['coin']:8s}  баланс={c['walletBalance']}  доступно={available}")

    click.echo("\nЕсли FUND показывает баланс, а UNIFIED = 0:")
    click.echo("  testnet.bybit.com → Assets → Transfer → Funding → Unified Trading")
    click.echo()


@cli.command()
def account():
    """Полный обзор счёта: equity, маржа, монеты, позиции."""
    acc = exchange.get_account()
    if not acc:
        click.echo("Не удалось получить данные счёта.")
        return

    click.echo(f"\n{'─'*40}")
    click.echo(f"  Режим:     {'DEMO' if config.TESTNET else 'REAL'}")
    click.echo(f"  Аккаунт:   {acc['account_type']}")
    click.echo(f"  Equity:    {float(acc['equity']):>12.2f} USDT")
    click.echo(f"  Маржа:     {float(acc['margin_bal']):>12.2f} USDT")
    click.echo(f"  Доступно:  {float(acc['available']):>12.2f} USDT")
    click.echo(f"  Perp PnL:  {float(acc['perp_upnl']):>+12.4f} USDT")
    click.echo(f"{'─'*40}\n")

    if acc["coins"]:
        rows = [
            [c["coin"], f"{float(c['balance']):.6f}",
             f"{float(c['available']):.6f}",
             f"{float(c['usd_value']):.2f}",
             f"{float(c['pnl']):+.4f}"]
            for c in acc["coins"]
        ]
        click.echo(tabulate(rows, headers=["Монета", "Баланс", "Доступно", "USD", "PnL"]))

    positions = [p for p in exchange.get_positions() if float(p.get("size", 0)) != 0]
    if positions:
        click.echo("\nОткрытые позиции:")
        rows = [
            [p["symbol"], p["side"], p["size"],
             p["avgPrice"], f"{float(p['unrealisedPnl']):+.4f}", p["leverage"] + "x"]
            for p in positions
        ]
        click.echo(tabulate(rows, headers=["Символ", "Сторона", "Объём", "Цена", "PnL", "Плечо"]))

    click.echo()


@cli.command()
@click.option("--limit", default=20, show_default=True, help="Кол-во последних сделок")
def history(limit: int):
    """История исполненных сделок из БД."""
    database.init()
    trades = database.get_trades(limit)
    if not trades:
        click.echo("Нет записей в истории.")
        return
    rows = [
        [t["ts"][:19], t["symbol"], t["side"],
         f"{t['qty']:.4f}", f"{t['price']:.2f}"]
        for t in trades
    ]
    click.echo(tabulate(rows, headers=["Время (UTC)", "Символ", "Сторона", "Объём", "Цена"]))
    click.echo()


# ── Ручные команды ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("symbol")
def price(symbol: str):
    """Текущая цена. Пример: python bot.py price BTCUSDT"""
    d = exchange.get_ticker(symbol.upper())
    click.echo(f"{d['symbol']}  last={d['lastPrice']}  bid={d['bid1Price']}  ask={d['ask1Price']}")


@cli.command()
@click.option("--coin", default="USDT", show_default=True)
def balance(coin: str):
    """Баланс кошелька."""
    info = exchange.get_balance(coin.upper())
    if not info:
        click.echo(f"Нет данных по {coin}")
        return
    rows = [["Кошелёк", info["wallet_balance"]],
            ["Доступно", info["available_balance"]],
            ["PnL",      info["unrealized_pnl"]]]
    click.echo(tabulate(rows))


@cli.command()
@click.option("--symbol", default=None)
def positions(symbol: str):
    """Открытые позиции."""
    data = [p for p in exchange.get_positions(symbol) if float(p.get("size", 0)) != 0]
    if not data:
        click.echo("Нет открытых позиций.")
        return
    rows = [[p["symbol"], p["side"], p["size"], p["avgPrice"], p["unrealisedPnl"]] for p in data]
    click.echo(tabulate(rows, headers=["Символ", "Сторона", "Объём", "Цена", "PnL"]))


@cli.command()
@click.option("--symbol", default=None)
def orders(symbol: str):
    """Открытые ордера."""
    data = exchange.get_open_orders(symbol)
    if not data:
        click.echo("Нет открытых ордеров.")
        return
    rows = [[o["orderId"][:12], o["symbol"], o["side"], o["orderType"],
             o["qty"], o.get("price", "—")] for o in data]
    click.echo(tabulate(rows, headers=["ID", "Символ", "Сторона", "Тип", "Объём", "Цена"]))


@cli.command()
@click.argument("symbol")
@click.argument("qty")
@click.option("--type", "order_type", type=click.Choice(["market", "limit"]), default="market")
@click.option("--price", "order_price", default=None)
def buy(symbol: str, qty: str, order_type: str, order_price: str):
    """Купить. Пример: python bot.py buy BTCUSDT 0.001"""
    r = exchange.place_order("Buy", symbol.upper(), qty, order_type.capitalize(), order_price)
    click.echo(f"Ордер создан: {r['orderId']}")


@cli.command()
@click.argument("symbol")
@click.argument("qty")
@click.option("--type", "order_type", type=click.Choice(["market", "limit"]), default="market")
@click.option("--price", "order_price", default=None)
@click.option("--reduce", is_flag=True, default=False)
def sell(symbol: str, qty: str, order_type: str, order_price: str, reduce: bool):
    """Продать. Пример: python bot.py sell BTCUSDT 0.001"""
    r = exchange.place_order("Sell", symbol.upper(), qty, order_type.capitalize(), order_price, reduce)
    click.echo(f"Ордер создан: {r['orderId']}")


@cli.command()
@click.argument("symbol")
@click.argument("order_id")
def cancel(symbol: str, order_id: str):
    """Отменить ордер."""
    r = exchange.cancel_order(symbol.upper(), order_id)
    click.echo(f"Отменён: {r}")


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _setup_logging():
    from pathlib import Path
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/logs/bot.log", encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    cli()
