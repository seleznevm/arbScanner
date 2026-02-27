from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import aiohttp

from arbscanner.config import Settings
from arbscanner.services.broker import BaseOpportunityBroker

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatState:
    last_send_ts: float = 0.0


class TelegramNotifier:
    def __init__(self, settings: Settings, broker: BaseOpportunityBroker) -> None:
        self.settings = settings
        self.broker = broker
        self._task: asyncio.Task[None] | None = None
        self._chat_state: dict[str, ChatState] = {}
        self._last_signal_ts: dict[str, float] = {}
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        queue = self.broker.subscribe()
        self._task = asyncio.create_task(self._run(queue), name="telegram-notifier")
        LOGGER.info("Telegram notifier started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        LOGGER.info("Telegram notifier stopped")

    async def _run(self, queue: asyncio.Queue[list[dict[str, object]]]) -> None:
        while True:
            payload = await queue.get()
            if not payload:
                continue

            filtered = self._debounce(payload)
            if not filtered:
                continue

            message = self._format_digest(filtered[: self.settings.telegram_max_rows])
            await self._broadcast(message)

    def _debounce(self, payload: list[dict[str, object]]) -> list[dict[str, object]]:
        now = time.time()
        result: list[dict[str, object]] = []
        for item in payload:
            key = str(item.get("id", "unknown"))
            last_seen = self._last_signal_ts.get(key, 0.0)
            # 15 seconds ~= 3 scan cycles in default config.
            if now - last_seen < 15.0:
                continue
            self._last_signal_ts[key] = now
            result.append(item)
        return result

    async def _broadcast(self, text: str) -> None:
        token = self.settings.telegram_bot_token
        chat_ids = self.settings.telegram_chat_ids
        if not token or not chat_ids:
            LOGGER.info("Telegram digest (dry-run):\n%s", text)
            return

        async with aiohttp.ClientSession() as session:
            for chat_id in chat_ids:
                if not self._can_send(chat_id):
                    continue
                await self._send_message(session, token, chat_id, text)

    def _can_send(self, chat_id: str) -> bool:
        now = time.time()
        state = self._chat_state.setdefault(chat_id, ChatState())
        if now - state.last_send_ts < self.settings.telegram_min_interval_sec:
            return False
        state.last_send_ts = now
        return True

    async def _send_message(
        self,
        session: aiohttp.ClientSession,
        token: str,
        chat_id: str,
        text: str,
    ) -> None:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with session.post(url, json=payload, timeout=8) as response:
                if response.status >= 400:
                    body = await response.text()
                    LOGGER.warning(
                        "Telegram send failed for chat %s: %s %s",
                        chat_id,
                        response.status,
                        body,
                    )
        except asyncio.TimeoutError:
            LOGGER.warning("Telegram send timeout for chat %s", chat_id)
        except Exception:
            LOGGER.exception("Telegram send error for chat %s", chat_id)

    @staticmethod
    def _format_digest(rows: list[dict[str, object]]) -> str:
        lines = ["<b>Arbitrage digest</b>"]
        for row in rows:
            lines.append(
                (
                    f"• <b>{row.get('symbol')}</b> "
                    f"{row.get('buy_exchange')} -> {row.get('sell_exchange')} | "
                    f"net: {float(row.get('net_edge_pct', 0.0)):.3f}% | "
                    f"qty: {float(row.get('available_qty', 0.0)):.4f}"
                )
            )
        return "\n".join(lines)

