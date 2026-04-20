# Bybit Trading Bot

Автоматический торговый бот для Bybit (USDT-перпетуалы). Поддерживает несколько стратегий одновременно с изолированными бюджетами и независимым риск-менеджментом. Запускается через Docker.

**Доступные стратегии:**
- **Grid** — ставит сетку лимитных ордеров, зарабатывает на боковом рынке
- **DCA** — накапливает позицию регулярными покупками, закрывает по take-profit

---

## Быстрый старт

### 1. Получи API-ключи Bybit

**Demo (testnet):**
1. Зайди на [testnet.bybit.com](https://testnet.bybit.com)
2. Account → API Management → Create New Key
3. Включи разрешения: **Read**, **Trade**
4. Сохрани `API Key` и `API Secret`

> После получения баланса на testnet — проверь, что средства в **Unified Trading** (не в Funding).  
> Если в Funding: Assets → Transfer → Funding → Unified Trading.

**Mainnet (реальные деньги):**
1. Зайди на [bybit.com](https://www.bybit.com)
2. Те же шаги, `BYBIT_TESTNET=false` в `.env`

---

### 2. Настрой окружение

```bash
git clone https://<TOKEN>@github.com/foofighterbass/bybit-trade.git
cd bybit-trade
cp .env.example .env
```

Открой `.env` и заполни:

```env
BYBIT_API_KEY=your_key_here
BYBIT_API_SECRET=your_secret_here
BYBIT_TESTNET=true               # true = demo, false = реальные деньги

DATABASE_URL=postgresql://bot:botpass@db:5432/botdb   # оставь по умолчанию

MAX_DAILY_LOSS_PCT=5             # дефолт, переопределяется в strategies.json
MAX_DRAWDOWN_PCT=20

POLL_INTERVAL=30                 # секунд между проверками ордеров
```

> Параметры стратегий (`symbol`, `levels`, `qty` и т.д.) задаются в `strategies.json`, не в `.env`.

---

### 3. Установи Docker

**Ubuntu (сервер):**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

**Mac:** скачай [Docker Desktop](https://www.docker.com/products/docker-desktop/)

---

### 4. Запусти бота

```bash
# Собрать образ и запустить в фоне
docker compose up -d --build

# Проверить что бот работает
docker compose logs -f
```

При старте бот автоматически применяет новые миграции БД — данные не теряются.  
Бот запускается автоматически при рестарте сервера (`restart: unless-stopped`).

---

## Управление

```bash
# Логи в реальном времени
docker compose logs -f

# Статус: виртуальные балансы, PnL, активные ордера
docker compose exec bot python bot.py status

# Полный обзор счёта
docker compose exec bot python bot.py account

# Остановить бота (Grid-ордера на бирже отменятся)
docker compose stop

# Перезапустить с пересборкой после изменений кода
docker compose up -d --build

# Сбросить сетку и построить заново (если цена ушла далеко)
docker compose exec bot python bot.py start --reset
```

---

## Ручные команды

```bash
docker compose exec bot python bot.py price BTCUSDT      # текущая цена
docker compose exec bot python bot.py balance            # баланс USDT
docker compose exec bot python bot.py positions          # открытые позиции
docker compose exec bot python bot.py orders             # активные ордера
docker compose exec bot python bot.py history            # история сделок из БД
docker compose exec bot python bot.py history --strategy dca_btc
docker compose exec bot python bot.py wallets            # диагностика кошельков

# Ручные сделки
docker compose exec bot python bot.py buy  BTCUSDT 0.001
docker compose exec bot python bot.py sell BTCUSDT 0.001
```

---

## Структура проекта

```
bybit-trade/
├── bot.py               # точка входа, весь CLI
├── config.py            # настройки из .env
├── strategies.json      # конфиг стратегий: параметры, капитал, вкл/выкл
│
├── core/                # инфраструктура
│   ├── database.py      # PostgreSQL + система миграций
│   ├── risk.py          # риск-менеджер (работает с виртуальным балансом)
│   └── runner.py        # запуск стратегий в потоках + watchdog
│
├── exchange/            # всё про биржу
│   ├── __init__.py      # публичный API
│   └── bybit.py         # Bybit API (pybit v5)
│
├── strategies/          # торговые стратегии
│   ├── __init__.py      # REGISTRY: {"grid": ..., "dca": ...}
│   ├── base.py          # абстрактный класс BaseStrategy
│   ├── grid/
│   │   └── strategy.py  # Grid Trading стратегия
│   └── dca/
│       └── strategy.py  # DCA стратегия (накопление + take-profit)
│
├── migrations/          # SQL-миграции схемы БД
│   ├── 001_initial.sql
│   └── 002_strategy_wallets.sql
│
├── data/logs/           # логи (volume, не в git)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

> База данных хранится в Docker volume `pgdata` (контейнер `bybit-db`).  
> Данные переживают рестарт и пересборку контейнеров.

---

## Управление стратегиями

Все стратегии описаны в `strategies.json`. Каждая стратегия работает с **изолированным виртуальным бюджетом** — риск-менеджер следит за просадкой именно виртуального баланса этой стратегии, а не всего счёта.

```json
[
  {
    "id": "grid_btc",
    "type": "grid",
    "enabled": true,
    "capital_usdt": 1000,
    "max_daily_loss_pct": 5,
    "max_drawdown_pct": 20,
    "params": { "symbol": "BTCUSDT", "levels": 5, "spacing_pct": 0.5, "qty": "0.001" }
  },
  {
    "id": "dca_btc",
    "type": "dca",
    "enabled": false,
    "capital_usdt": 500,
    "max_daily_loss_pct": 3,
    "max_drawdown_pct": 15,
    "params": {
      "symbol": "BTCUSDT",
      "order_qty": "0.001",
      "interval_hours": 6,
      "dip_pct": 1.0,
      "take_profit_pct": 2.0,
      "max_orders": 8
    }
  }
]
```

```bash
# Запустить все enabled=true стратегии
docker compose exec bot python bot.py start

# Запустить только одну
docker compose exec bot python bot.py start --strategy grid_btc

# Список всех стратегий с параметрами
docker compose exec bot python bot.py strategies

# Выключить стратегию: поставить "enabled": false, затем
docker compose restart bot
```

Чтобы добавить новую стратегию:
1. Создай `strategies/<name>/strategy.py` с классом от `BaseStrategy`
2. Зарегистрируй в `strategies/__init__.py`
3. Добавь запись в `strategies.json`

---

## Grid стратегия

Бот ставит лимитные ордера выше и ниже текущей цены с шагом `spacing_pct`:

- Исполнился **BUY** → ставит **SELL** на `spacing_pct%` выше
- Исполнился **SELL** → ставит **BUY** на `spacing_pct%` ниже
- Прибыль за цикл = `qty × price × spacing_pct%`

**Когда перестраивать сетку (`--reset`):**
- Цена вышла за диапазон (все ордера одной стороны исполнились)
- Рынок сдвинулся > 5% от центра сетки

**Настройка `spacing_pct` под волатильность:**
- 0 сделок в день → уменьши (0.5% → 0.3%)
- Много сделок но малый PnL → увеличь (0.5% → 0.8%)
- Норма: 3–10 сделок в день

---

## DCA стратегия

Накапливает позицию регулярными покупками, закрывает разом при достижении take-profit.

**Параметры:**

| Параметр | Описание |
|---|---|
| `order_qty` | Объём одной DCA-покупки |
| `interval_hours` | Минимальный интервал между покупками |
| `dip_pct` | Покупать только при откате на X% от предыдущей покупки (0 = отключено) |
| `take_profit_pct` | Закрыть всю позицию при росте средней цены на X% |
| `max_orders` | Максимум накопленных покупок (защита от бесконечного усреднения) |

**Когда работает лучше:** в растущем или умеренно боковом рынке. Дополняет Grid: Grid зарабатывает на флэте, DCA — на тренде.

**Важно при остановке:** DCA не отменяет открытую позицию автоматически. Закрыть вручную:
```bash
docker compose exec bot python bot.py sell BTCUSDT <qty> --reduce
```

---

## Виртуальные бюджеты стратегий

Каждая стратегия работает в рамках своего `capital_usdt`. Бот ведёт `virtual_balance` — текущий баланс стратегии с учётом накопленного PnL.

- `MAX_DAILY_LOSS_PCT` — стоп если дневной убыток превысил X% от `capital_usdt`
- `MAX_DRAWDOWN_PCT` — стоп если `virtual_balance` просел на X% от исторического пика

Просмотр текущих балансов:
```bash
docker compose exec bot python bot.py status
```

---

## Миграции базы данных

При изменении схемы создаются пронумерованные SQL-файлы в папке `migrations/`.  
При каждом старте бот автоматически применяет только новые миграции — данные не затрагиваются.

```bash
# Просмотр применённых миграций
docker compose exec db psql -U bot -d botdb \
  -c "SELECT filename, applied_at FROM schema_migrations ORDER BY filename;"
```

**Правило:** существующие файлы миграций не редактировать — только добавлять новые.

---

## Запросы к базе данных

```bash
# Подключиться к PostgreSQL
docker compose exec db psql -U bot -d botdb

# Виртуальные балансы стратегий
SELECT strategy_id, capital_usdt, virtual_balance,
       round((virtual_balance - capital_usdt)::numeric, 2) AS all_time_pnl
  FROM strategy_wallets ORDER BY strategy_id;

# Дневной PnL
SELECT date, strategy_id, trades, round(realized::numeric, 4)
  FROM daily_pnl ORDER BY date DESC, strategy_id;

# Активные Grid-ордера
SELECT side, count(*), min(price), max(price)
  FROM grid_orders WHERE status='active' GROUP BY side;

# История баланса
SELECT ts, balance, equity FROM balance_history ORDER BY id DESC LIMIT 20;
```

---

## Деплой на сервер

> Bybit Testnet блокирует US IP — используй сервер **не в США**.  
> Текущий сервер: AWS eu-west-1 (Ирландия) `63.32.93.247`

```bash
# Подключиться по SSH
ssh -i ~/.ssh/eu-west-1.pem ubuntu@63.32.93.247

# Обновить код и перезапустить
git pull && docker compose up -d --build
```

---

## Observability

Признаки нормальной работы в логах:
```
[grid_btc] alive | virtual_balance=1043.20 | account=9987.50 equity=9987.50
[grid_btc] Исполнен Sell @ 85423.0  pnl=+0.4271
```

Признаки проблем:
```
[watchdog] Поток grid_btc мёртв — перезапускаю      ← поток упал, watchdog поднял
[grid_btc] СТОП: Дневной убыток ...                 ← сработал риск-стоп
[grid_btc] Сетка пустая — перестраиваю              ← все ордера исполнились
```

```bash
# Фильтр по ключевым событиям
docker compose logs | grep -E "СТОП|мёртв|Исполнен|alive|Ошибка"
```
