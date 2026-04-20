#!/usr/bin/env python3
"""
Точка входа.

  python bot.py start                        # запустить все включённые стратегии
  python bot.py start --strategy grid_btc    # запустить одну стратегию
  python bot.py start --reset                # сбросить сетки и начать заново
  python bot.py status                       # PnL по всем стратегиям + ордера
  python bot.py strategies                   # список стратегий из strategies.json

  python bot.py set-symbol grid_btc ETHUSDT  # сменить торговую пару стратегии

  python bot.py price BTCUSDT
  python bot.py balance
  python bot.py positions
  python bot.py orders
  python bot.py history [--strategy grid_btc]
  python bot.py buy  BTCUSDT 0.001 [--type limit --price 60000]
  python bot.py sell BTCUSDT 0.001 [--type limit --price 65000]
  python bot.py cancel BTCUSDT <order_id>
"""
import json
import logging
import signal
import sys

import click
from tabulate import tabulate

import config
import exchange
from core import database
from core.runner import StrategyRunner, load_configs

log = logging.getLogger(__name__)


# ── Автобот ───────────────────────────────────────────────────────────────────

@click.group()
def cli():
    pass


@cli.command()
@click.option("--reset",    is_flag=True, default=False, help="Пересобрать сетки с нуля")
@click.option("--strategy", default=None, help="ID конкретной стратегии (иначе все включённые)")
def start(reset: bool, strategy: str):
    """Запустить стратегии."""
    _setup_logging()
    database.init()

    runner = StrategyRunner()

    def on_signal(*_):
        nonlocal runner
        log.info("Остановка всех стратегий...")
        runner.stop_all()

    signal.signal(signal.SIGINT,  on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    runner.start(reset=reset, only=strategy)
    runner.wait()
    log.info("Бот остановлен.")


@cli.command()
def strategies():
    """Список стратегий из strategies.json."""
    cfgs = load_configs()
    rows = [
        [
            c["id"],
            c["type"],
            "✓" if c.get("enabled", True) else "✗",
            c.get("capital_usdt", "—"),
            c.get("max_daily_loss_pct", config.MAX_DAILY_LOSS_PCT),
            c.get("max_drawdown_pct",   config.MAX_DRAWDOWN_PCT),
            str(c.get("params", {})),
        ]
        for c in cfgs
    ]
    click.echo(tabulate(
        rows,
        headers=["ID", "Тип", "Вкл", "Капитал", "Loss%", "DD%", "Параметры"],
    ))
    click.echo()


@cli.command("set-symbol")
@click.argument("strategy_id")
@click.argument("symbol")
def set_symbol(strategy_id: str, symbol: str):
    """Сменить торговую пару стратегии.

    Отменяет все открытые ордера старой пары на бирже и в БД,
    обновляет strategies.json. После этого нужен рестарт бота.

    Пример:
      python bot.py set-symbol grid_btc ETHUSDT
    """
    database.init()
    symbol = symbol.upper()

    cfgs = load_configs()
    cfg  = next((c for c in cfgs if c["id"] == strategy_id), None)
    if not cfg:
        click.echo(f"Стратегия '{strategy_id}' не найдена в strategies.json.")
        return

    old_symbol = cfg.get("params", {}).get("symbol", "").upper()
    if not old_symbol:
        click.echo("У стратегии нет параметра 'symbol'.")
        return

    if old_symbol == symbol:
        click.echo(f"Символ уже установлен: {symbol}. Ничего не изменено.")
        return

    # Проверяем что новый символ существует на бирже
    try:
        ticker = exchange.get_ticker(symbol)
        current_price = ticker["lastPrice"]
    except Exception as exc:
        click.echo(f"Символ {symbol} не найден на бирже: {exc}")
        return

    click.echo(f"\nСмена символа для [{strategy_id}]: {old_symbol} → {symbol}")
    click.echo(f"Текущая цена {symbol}: {current_price}\n")

    # Отменяем ордера старой пары на бирже
    cancelled_exchange = 0
    try:
        open_orders = exchange.get_open_orders(old_symbol)
        for o in open_orders:
            try:
                exchange.cancel_order(old_symbol, o["orderId"])
                cancelled_exchange += 1
            except Exception as exc:
                click.echo(f"  Не удалось отменить {o['orderId']}: {exc}")
        click.echo(f"Отменено на бирже: {cancelled_exchange} ордеров {old_symbol}")
    except Exception as exc:
        click.echo(f"Ошибка при получении ордеров с биржи: {exc}")

    # Помечаем ордера отменёнными в БД
    database.cancel_all_orders(strategy_id, old_symbol)
    click.echo(f"Ордера {old_symbol} помечены cancelled в БД.")

    # Обновляем strategies.json
    cfg["params"]["symbol"] = symbol
    with open("strategies.json", "w", encoding="utf-8") as f:
        json.dump(cfgs, f, indent=2, ensure_ascii=False)
        f.write("\n")
    click.echo(f"strategies.json обновлён: {old_symbol} → {symbol}")

    click.echo(f"\nГотово. Перезапусти бота:")
    click.echo(f"  docker compose restart bot")


@cli.command()
def status():
    """PnL всех стратегий за сегодня + виртуальные балансы + активные ордера."""
    database.init()

    click.echo(f"\nРежим: {'DEMO' if config.TESTNET else 'REAL'}")
    bal = exchange.get_balance("USDT")
    click.echo(f"Баланс счёта: {bal.get('available_balance', '?')} USDT\n")

    wallets = database.get_wallets_summary()
    if wallets:
        pnls = {p["strategy_id"]: p for p in database.get_all_daily_pnl()}
        click.echo("── Стратегии ──")
        rows = []
        for w in wallets:
            sid   = w["strategy_id"]
            p     = pnls.get(sid, {})
            pnl   = p.get("realized", 0.0)
            trade = p.get("trades", 0)
            profit = w["virtual_balance"] - w["capital_usdt"]
            rows.append([
                sid,
                f"{w['capital_usdt']:.0f}",
                f"{w['virtual_balance']:.2f}",
                f"{profit:+.2f}",
                trade,
                f"{pnl:+.4f}",
            ])
        click.echo(tabulate(
            rows,
            headers=["Стратегия", "Капитал", "Виртуал. баланс", "All-time PnL", "Сделок сегодня", "PnL сегодня"],
        ))
        click.echo()

    for cfg in load_configs():
        sid    = cfg["id"]
        symbol = cfg.get("params", {}).get("symbol")
        if not symbol:
            continue
        orders = database.load_active_orders(sid, symbol)
        if orders:
            click.echo(f"── Ордера [{sid}] ──")
            rows = [[o["side"], o["price"], o["qty"], o["created_at"][:19]] for o in orders]
            click.echo(tabulate(rows, headers=["Сторона", "Цена", "Объём", "Создан"]))
            click.echo()


# ── Информация о счёте ────────────────────────────────────────────────────────

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
@click.option("--limit",    default=20,   show_default=True)
@click.option("--strategy", default=None, help="Фильтр по ID стратегии")
def history(limit: int, strategy: str):
    """История исполненных сделок из БД."""
    database.init()
    trades = database.get_trades(limit, strategy_id=strategy)
    if not trades:
        click.echo("Нет записей в истории.")
        return
    rows = [
        [t["ts"][:19], t["strategy_id"], t["symbol"], t["side"],
         f"{t['qty']:.4f}", f"{t['price']:.2f}"]
        for t in trades
    ]
    click.echo(tabulate(rows, headers=["Время (UTC)", "Стратегия", "Символ", "Сторона", "Объём", "Цена"]))
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
@click.option("--type",  "order_type",  type=click.Choice(["market", "limit"]), default="market")
@click.option("--price", "order_price", default=None)
def buy(symbol: str, qty: str, order_type: str, order_price: str):
    """Купить. Пример: python bot.py buy BTCUSDT 0.001"""
    r = exchange.place_order("Buy", symbol.upper(), qty, order_type.capitalize(), order_price)
    click.echo(f"Ордер создан: {r['orderId']}")


@cli.command()
@click.argument("symbol")
@click.argument("qty")
@click.option("--type",   "order_type",  type=click.Choice(["market", "limit"]), default="market")
@click.option("--price",  "order_price", default=None)
@click.option("--reduce", is_flag=True,  default=False)
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


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _setup_logging():
    from pathlib import Path
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/logs/bot.log", encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    cli()
