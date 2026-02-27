# Backlog (MVP -> v2)

## Цели MVP (итерация 1)
- `Detection-only`: поиск возможностей без автоисполнения ордеров.
- 5-секундный цикл пересчета рынка.
- Единый канонический формат ордербуков и сигналов.
- Web UI + Telegram уведомления.
- Наблюдаемость и базовая безопасность.

## Приоритизация (P0/P1/P2)

### P0 - обязательно для релиза MVP
1. Платформенный каркас
- Docker Compose: `api`, `worker`, `redis`, `postgres`.
- Конфигурация через env и единая модель настроек.
- Базовые health-check эндпоинты.

2. Ядро данных и коннекторы
- Абстракция коннектора биржи: `snapshot + delta`, health metadata.
- Каноническая модель `OrderBookSnapshot`.
- Хранилище горячих данных (Redis + in-memory fallback).
- Реализация минимум 2 рабочих коннекторов (на старте - mock для валидации пайплайна).

3. Математическое ядро
- VWAP для buy/sell стороны с частичным заполнением уровня.
- Пространственный арбитраж (межбиржевой) с учетом:
- taker fee (две стороны),
- slippage budget,
- withdrawal/rebalance cost.
- Фильтрация по `min_net_edge_pct`.
- Цикл пересчета строго каждые 5 секунд.

4. Backend API и realtime
- `GET /health`.
- `GET /api/opportunities` (актуальный срез).
- `WS /ws/opportunities` (push обновлений).
- Публикация/подписка через event feed `opportunities_feed`.

5. Telegram-оповещения (базовый контур)
- Подписка воркера на feed.
- Smart batching (дайджест за цикл).
- Debounce одинаковых сигналов.
- Мягкий rate-limit per chat.

6. БД и схема
- PostgreSQL таблицы: `users`, `api_credentials`, `strategy_config`, `instruments_dict`, `arbitrage_log`.
- Хранение `arbitrage_log` как базовый аудит сигналов.

7. Безопасность (база MVP)
- JWT auth для web-панели (минимум backend-ready контракты).
- Шифрование API credentials на уровне приложения.
- Валидация прав ключей только `Read-Only`.

8. Наблюдаемость
- Экспорт метрик: `md_lag_ms`, `ws_reconnects_total`, `orderbook_gap_events`, `opportunities_detected_per_minute`.
- Логи по коннекторам и scan-loop.

### P1 - сразу после MVP
1. Реальные коннекторы Tier-1
- Binance, OKX, Kraken, Bybit, Coinbase с их требованиями по целостности.
- Механики seq/checksum/re-sync по каждой бирже.

2. Реальные коннекторы Tier-2/3
- KuCoin, Gate, MEXC, Bitget, HTX, Upbit, BingX, Bitfinex, XT.

3. Triangular arbitrage
- Граф активов, трансформация через `-log(rate)`.
- Bellman-Ford для поиска отрицательных циклов.
- Фильтры по `lotSize/tickSize`.

4. UX Dashboard v1
- ArbMatrix 14x14.
- Health board по всем коннекторам.
- Progressive disclosure калькуляции комиссии/slippage.

5. Полноценный auth+RBAC
- Access/Refresh JWT rotation.
- 2FA (TOTP) для admin/trader.

### P2 - v2 и production hardening
1. Replay/backtesting на исторических данных.
2. SLO/SLI и полноценные алерты Grafana.
3. Compliance-контур (KYC/AML audit hooks, delisting policies).
4. Подготовка execution-ready интерфейсов под Smart Order Routing.

## Декомпозиция на спринты (предложение)
1. Спринт 1 (1 неделя)
- Каркас сервисов, модели, scan-loop, mock data, API/WS.
2. Спринт 2 (1-2 недели)
- Tier-1 коннекторы (минимум Binance+OKX), Redis/Postgres интеграция, Telegram worker.
3. Спринт 3 (1 неделя)
- UX dashboard, безопасность (JWT + secrets), метрики.
4. Спринт 4 (1-2 недели)
- Остальные биржи + triangular engine + нагрузочные тесты.

## Definition of Done (MVP)
- 5-секундный цикл стабилен >= 24h без падений.
- API/WS отдает валидные сигналы с net edge.
- Telegram не нарушает лимиты и не спамит дубликатами.
- Базовые интеграционные тесты проходят.
- Развертывание через `docker compose up -d` воспроизводимо.
