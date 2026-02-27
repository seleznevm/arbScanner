from __future__ import annotations

import asyncio
import logging

from arbscanner.config import Settings
from arbscanner.services.broker import build_broker
from arbscanner.services.scanner import ScannerRuntime
from arbscanner.services.telegram_notifier import TelegramNotifier


async def run_worker() -> None:
    settings = Settings.from_env()
    broker = build_broker(settings)
    scanner = ScannerRuntime(settings=settings, broker=broker)
    notifier = TelegramNotifier(settings=settings, broker=broker)

    await scanner.start()
    await notifier.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await notifier.stop()
        await scanner.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

