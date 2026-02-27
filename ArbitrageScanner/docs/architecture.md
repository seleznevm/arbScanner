# Архитектура MVP (Итерация 1)

## 1. Контуры системы
- `Market Data Ingestion`: коннекторы бирж поддерживают локальные L2 книги и передают нормализованные снимки.
- `Caching & Eventing`: Redis (или in-memory fallback) хранит горячие данные и рассылает feed сигналов.
- `Decisioning`: движок арбитража раз в 5 секунд строит когерентный срез и вычисляет net opportunities.
- `Delivery`: FastAPI (REST/WS) и Telegram notifier.

## 2. Логическая схема потоков
1. Коннектор получает `snapshot + delta` от биржи.
2. Обновляет локальный `OrderBookSnapshot` в каноническом формате.
3. `ScannerRuntime` каждые 5 секунд читает все актуальные книги.
4. `OpportunityEngine` считает VWAP и net edge.
5. Пул возможностей публикуется в `opportunities_feed`.
6. API отправляет обновления в WebSocket клиентов.
7. Telegram worker забирает feed, фильтрует и отправляет digest.

## 3. Каноническая модель данных

### 3.1 OrderBookSnapshot
- `exchange`: имя площадки (`binance`, `okx`, ...).
- `symbol`: унифицированный инструмент (`BTC-USDT`).
- `bids` / `asks`: массивы уровней `[price, qty]`.
- `ts_event`: timestamp биржи.
- `ts_ingest`: timestamp сервера.
- `is_healthy`: статус целостности стакана.
- `meta`: служебные поля (`seq_id`, `checksum_ok`, `lag_ms`).

### 3.2 Opportunity
- `type`: `spatial` (в MVP), `triangular` (позже).
- `symbol`.
- `buy_exchange`, `sell_exchange`.
- `buy_vwap`, `sell_vwap`.
- `gross_edge_pct`, `net_edge_pct`.
- `expected_profit_usdt`.
- `available_qty`.
- `risk_flag`.
- `ts_detected`.

## 4. Алгоритмический контур

### 4.1 VWAP
- Для целевого объема движок проходит уровни стакана сверху вниз.
- На граничном уровне берет только необходимую часть объема.
- Возвращает `(vwap, filled_qty)`; при недостатке ликвидности сигнал отбрасывается.

### 4.2 Spatial arbitrage
- Для каждой пары бирж `A -> B`:
- покупка на `A` по `ask_vwap`,
- продажа на `B` по `bid_vwap`.
- Net edge:
- `gross = (sell_vwap - buy_vwap) / buy_vwap * 100`
- `fees_pct = 2 * taker_fee_bps / 100`
- `slippage_pct = slippage_bps / 100`
- `withdraw_pct = withdraw_cost_usdt / (buy_vwap * qty) * 100`
- `net = gross - fees_pct - slippage_pct - withdraw_pct`
- Сигнал валиден, если `net >= min_net_edge_pct`.

### 4.3 Triangular (roadmap)
- Граф активов внутри биржи.
- Вес ребра: `-log(effective_rate_after_fees)`.
- Поиск отрицательных циклов Bellman-Ford.

## 5. Инфраструктура контейнеров
- `api`: FastAPI + WebSocket.
- `worker`: scanner runtime + telegram notifier.
- `redis`: event bus и shared state.
- `postgres`: настройки/аудит (каркас под дальнейшее подключение ORM/migrations).

## 6. Надежность
- Изоляция коннекторов: падение одной биржи не останавливает движок.
- Staleness filter: книги старше `stale_after_sec` исключаются.
- Переподключения conenctor-уровня с backoff (в roadmap для real connectors).

## 7. Безопасность (MVP baseline)
- JWT и 2FA в roadmap, backend-ready контуры заложены.
- API credentials только encrypted-at-rest.
- Сетевой периметр: наружу только `Nginx -> api`.

## 8. Наблюдаемость
- Бизнес-метрики:
- `opportunities_detected_per_minute`.
- `net_edge_distribution`.
- Технические метрики:
- `md_lag_ms`, `ws_reconnects_total`, `orderbook_gap_events`.

## 9. Ограничения текущей реализации
- Реальные WS/REST адаптеры всех 14 бирж еще не подключены (используются mock connectors).
- Triangular engine пока заглушка.
- PostgreSQL схема описана, но миграции и DAO слой отложены в следующий этап.
