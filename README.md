# Bybit Grid Trading Bot

Автоматический Grid-бот для торговли на Bybit (USDT-перпетуалы). Запускается через Docker.

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
# Клонируй репозиторий
git clone https://<TOKEN>@github.com/foofighterbass/bybit-trade.git
cd bybit-trade

# Создай .env из шаблона
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

PAPER_TRADING=false              # true = локальное тестирование без реальных ордеров
PAPER_PRICE_FEED=real            # real | random
PAPER_INITIAL_BALANCE=10000
PAPER_START_PRICE=84000          # только для random фида
PAPER_VOLATILITY=0.3             # % на тик, только для random фида
```

> Параметры стратегии (`symbol`, `levels`, `spacing_pct`, `qty`) задаются в `strategies.json`, не в `.env`.

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

Бот запустится автоматически при рестарте сервера (`restart: unless-stopped`).

---

## Управление

```bash
# Логи в реальном времени
docker compose logs -f

# Статус: активные ордера + дневной PnL
docker compose exec bot python bot.py status

# Полный обзор счёта
docker compose exec bot python bot.py account

# Остановить бота (ордера на бирже отменятся)
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
│   ├── database.py      # PostgreSQL: сделки, ордера, PnL, история баланса
│   ├── risk.py          # риск-менеджер
│   └── runner.py        # запуск стратегий в потоках
│
├── exchange/            # всё про биржу
│   ├── __init__.py      # публичный API
│   ├── bybit.py         # реальный Bybit API (pybit v5)
│   └── paper.py         # paper trading (симуляция)
│
├── strategies/          # торговые стратегии
│   ├── base.py          # абстрактный класс BaseStrategy
│   └── grid/
│       └── strategy.py  # Grid Trading стратегия
│
├── data/logs/           # логи (volume, не в git)
├── Dockerfile
├── docker-compose.yml   # два контейнера: bot + db (postgres:16-alpine)
├── requirements.txt
└── .env.example
```

> База данных хранится в Docker volume `pgdata` (контейнер `bybit-db`).  
> Данные переживают рестарт и пересборку контейнеров.

---

## Paper trading (локальное тестирование)

Позволяет запустить бота локально, не нарушая работу уже запущенного на сервере.  
Ордера **не отправляются** на биржу — хранятся локально. Исполнение симулируется по цене.

### Два режима ценового фида

| `PAPER_PRICE_FEED` | Описание | Нужны API ключи |
|---|---|---|
| `real` | Цена берётся с Bybit API (только GET-запросы) | Да (но только чтение) |
| `random` | Цена генерируется случайным блужданием | Нет |

### Быстрый старт (random — без API ключей)

```bash
cp .env.example .env
# Отредактируй .env:
PAPER_TRADING=true
PAPER_PRICE_FEED=random
PAPER_START_PRICE=84000   # стартовая цена BTC
PAPER_VOLATILITY=0.3      # % изменение за тик (30 сек)
PAPER_INITIAL_BALANCE=10000

# Запустить локальную БД и бота
docker compose up -d
```

### Быстрый старт (real — реальная цена, но без ордеров)

```bash
# В .env: твои обычные Bybit testnet ключи
PAPER_TRADING=true
PAPER_PRICE_FEED=real

docker compose up -d
```

> Ордера на биржу не отправляются в обоих случаях.  
> Локальная БД не пересекается с БД сервера.  
> Логи помечены `[PAPER]` для отличия от боевого режима.

---

## Управление стратегиями

Все стратегии описаны в `strategies.json`. Пример с двумя стратегиями:

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
    "id": "grid_eth",
    "type": "grid",
    "enabled": false,
    "capital_usdt": 500,
    "max_daily_loss_pct": 3,
    "max_drawdown_pct": 15,
    "params": { "symbol": "ETHUSDT", "levels": 4, "spacing_pct": 0.6, "qty": "0.01" }
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

# Выключить стратегию: поставить "enabled": false в strategies.json, затем
docker compose restart bot
```

Чтобы добавить новую стратегию:
1. Создай `strategies/<name>/strategy.py` с классом унаследованным от `BaseStrategy`
2. Зарегистрируй в `strategies/__init__.py`
3. Добавь запись в `strategies.json`

---

## Как работает Grid стратегия

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

**Когда остановить бота:**
- Сильный тренд 3+ дней подряд
- Просадка приближается к `MAX_DRAWDOWN_PCT`

---

## Запросы к базе данных

```bash
# Подключиться к PostgreSQL
docker compose exec db psql -U bot -d botdb

# Дневной PnL
SELECT date, trades, round(realized::numeric, 4) FROM daily_pnl ORDER BY date DESC;

# Активные ордера
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
