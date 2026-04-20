"""Всё общение с Bybit API."""
from __future__ import annotations
from typing import Optional
from pybit.unified_trading import HTTP
import config

_session: HTTP | None = None
_account_type_cache: str | None = None


def session() -> HTTP:
    global _session
    if _session is None:
        _session = HTTP(
            testnet=config.TESTNET,
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
        )
    return _session


def get_wallets_raw() -> dict[str, list]:
    """Возвращает сырые данные по всем кошелькам для диагностики."""
    result = {}
    try:
        data = session().get_wallet_balance(accountType="UNIFIED")["result"]["list"]
        result["UNIFIED (торговый)"] = data
    except Exception as exc:
        result["UNIFIED (торговый)"] = [{"error": str(exc)}]
    try:
        data = session().get_coins_balance(accountType="FUND", coin="USDT")["result"]
        result["FUND (депозитный)"] = [{"balance_raw": data}]
    except Exception as exc:
        result["FUND (депозитный)"] = [{"error": str(exc)}]
    return result


def _detect_account_type() -> str:
    global _account_type_cache
    if _account_type_cache:
        return _account_type_cache
    for account_type in ("UNIFIED", "CONTRACT", "SPOT"):
        try:
            data = session().get_wallet_balance(accountType=account_type)["result"]["list"]
            for acc in data:
                for coin in acc.get("coin", []):
                    if float(coin.get("walletBalance", 0)) > 0:
                        _account_type_cache = account_type
                        return account_type
        except Exception:
            continue
    _account_type_cache = "UNIFIED"
    return "UNIFIED"


def get_account() -> dict:
    account_type = _detect_account_type()
    data = session().get_wallet_balance(accountType=account_type)["result"]["list"]
    if not data:
        return {}
    acc = data[0]
    coins = [
        {
            "coin":      c["coin"],
            "balance":   c["walletBalance"],
            "available": c.get("availableToWithdraw") or c.get("equity") or c["walletBalance"],
            "usd_value": c.get("usdValue", "0"),
            "pnl":       c.get("unrealisedPnl", "0"),
        }
        for c in acc.get("coin", [])
        if float(c.get("walletBalance", 0)) != 0
    ]
    return {
        "account_type": account_type,
        "equity":       acc.get("totalEquity", "0"),
        "margin_bal":   acc.get("totalMarginBalance", "0"),
        "available":    acc.get("totalAvailableBalance", "0"),
        "perp_upnl":    acc.get("totalPerpUPL", "0"),
        "coins":        coins,
    }


def get_balance(coin: str = "USDT") -> dict:
    account_type = _detect_account_type()
    resp = session().get_wallet_balance(accountType=account_type, coin=coin)
    for account in resp["result"]["list"]:
        for item in account.get("coin", []):
            if item["coin"] == coin:
                available = item.get("availableToWithdraw") or item.get("equity") or item["walletBalance"]
                return {
                    "coin":              coin,
                    "wallet_balance":    item["walletBalance"],
                    "available_balance": available,
                    "unrealized_pnl":    item.get("unrealisedPnl", "0"),
                }
    return {}


def get_ticker(symbol: str) -> dict:
    items = session().get_tickers(category="linear", symbol=symbol)["result"]["list"]
    if not items:
        raise ValueError(f"Тикер {symbol} не найден")
    return items[0]


def get_positions(symbol: Optional[str] = None) -> list[dict]:
    kwargs: dict = {"category": "linear", "settleCoin": "USDT"}
    if symbol:
        kwargs["symbol"] = symbol
    return session().get_positions(**kwargs)["result"]["list"]


def get_open_orders(symbol: Optional[str] = None) -> list[dict]:
    kwargs: dict = {"category": "linear"}
    if symbol:
        kwargs["symbol"] = symbol
    else:
        kwargs["settleCoin"] = "USDT"
    return session().get_open_orders(**kwargs)["result"]["list"]


def place_order(
    side: str,
    symbol: str,
    qty: str,
    order_type: str = "Market",
    price: Optional[str] = None,
    reduce_only: bool = False,
) -> dict:
    if order_type == "Limit" and not price:
        raise ValueError("Для лимитного ордера нужна цена")
    kwargs: dict = {
        "category":    "linear",
        "symbol":      symbol,
        "side":        side,
        "orderType":   order_type,
        "qty":         qty,
        "timeInForce": "GTC" if order_type == "Limit" else "IOC",
        "reduceOnly":  reduce_only,
    }
    if price:
        kwargs["price"] = price
    return session().place_order(**kwargs)["result"]


def cancel_order(symbol: str, order_id: str) -> dict:
    return session().cancel_order(
        category="linear", symbol=symbol, orderId=order_id
    )["result"]
