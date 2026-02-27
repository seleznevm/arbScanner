# ArbitrageScanner MVP

Detection-only MVP для поиска крипто-спредов по ТЗ:
- 5-секундный цикл сканирования.
- Канонический формат ордербуков.
- VWAP + net edge расчет.
- REST + WebSocket API.
- Telegram notifier (batch + debounce).
- Docker compose окружение.

## Что реализовано
- `arbscanner/services/engine.py`: VWAP и spatial arbitrage.
- `arbscanner/services/scanner.py`: scan-loop и публикация возможностей.
- `arbscanner/services/broker.py`: Redis/in-memory event bus.
- `arbscanner/api/app.py`: FastAPI (`/health`, `/api/opportunities`, `/ws/opportunities`, `/`).
- `arbscanner/services/telegram_notifier.py`: digest-уведомления.
- `arbscanner/connectors/mock_connector.py`: mock-поток для 14 бирж.

## Быстрый запуск (локально)
1. Установить зависимости:
```bash
pip install -r requirements.txt
```
2. Запустить API (с встроенным сканером в одном процессе):
```bash
set RUN_SCANNER_IN_API=true
python ArbitrageScanner.py api
```
3. Открыть:
- `http://localhost:8000/`
- `http://localhost:8000/health`

## Запуск в docker compose
```bash
docker compose up --build
```
Сервисы:
- `api` на `:8000`
- `worker` (scanner + telegram)
- `redis`
- `postgres`

По умолчанию в compose:
- сканер работает в `worker`,
- `api` только читает feed из Redis.

## Telegram
Настроить в `.env.example`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS=12345,67890`

Без токена работает `dry-run` и пишет digest в логи.

## Ограничения текущей версии
- Реальные коннекторы бирж пока не подключены (используются mock-коннекторы).
- Triangular arbitrage оставлен как следующий milestone.
- Слой PostgreSQL схем и миграций еще не добавлен в код.

## Документация
- [Backlog](docs/backlog.md)
- [Architecture](docs/architecture.md)

## SQL-схема
- Базовый DDL: `db/schema.sql`
