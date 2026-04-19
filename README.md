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
BYBIT_TESTNET=true          # true = demo, false = реальные деньги

GRID_SYMBOL=BTCUSDT
GRID_LEVELS=5               # ордеров с каждой стороны от цены
GRID_SPACING_PCT=0.5        # % расстояния между уровнями
GRID_QTY=0.001              # объём одного ордера в BTC

MAX_DAILY_LOSS_PCT=5        # стоп если дневной убыток > 5%
MAX_DRAWDOWN_PCT=20         # стоп если просадка > 20%

POLL_INTERVAL=30            # секунд между проверками ордеров
```

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
├── bot.py          # точка входа, CLI, главный цикл
├── grid.py         # логика Grid-стратегии
├── risk.py         # риск-менеджер (дневной убыток + просадка)
├── exchange.py     # Bybit API (pybit v5)
├── database.py     # SQLite: сделки, ордера, PnL, история баланса
├── config.py       # все настройки из .env
├── data/           # SQLite БД + логи (volume, не в git)
│   ├── trades.db
│   └── logs/bot.log
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Как работает стратегия

Бот ставит лимитные ордера выше и ниже текущей цены с шагом `GRID_SPACING_PCT`:

- Исполнился **BUY** → ставит **SELL** на `spacing%` выше
- Исполнился **SELL** → ставит **BUY** на `spacing%` ниже
- Прибыль за цикл = `qty × price × spacing%`

**Когда перестраивать сетку (`--reset`):**
- Цена вышла за диапазон (все ордера одной стороны исполнились)
- Рынок сдвинулся > 5% от центра сетки

**Настройка spacing под волатильность:**
- 0 сделок в день → уменьши spacing (0.5% → 0.3%)
- Много сделок но малый PnL → увеличь spacing (0.5% → 0.8%)
- Норма: 3–10 сделок в день

**Когда остановить бота:**
- Сильный тренд 3+ дней подряд
- Просадка приближается к `MAX_DRAWDOWN_PCT`

---

## SQLite запросы

```bash
sqlite3 data/trades.db

# Дневной PnL
SELECT date, trades, round(realized,4) FROM daily_pnl ORDER BY date DESC;

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
