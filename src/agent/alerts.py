"""Alerting via Telegram (primary)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from agent.config import EnvSettings
from agent.logging_setup import get_logger

log = get_logger(__name__)


class Alerter(ABC):
    @abstractmethod
    async def send(self, message: str, level: str = "info") -> bool:
        pass


class TelegramAlerter(Alerter):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def send(self, message: str, level: str = "info") -> bool:
        prefix = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(level, "ℹ️")
        text = f"{prefix} {message}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url,
                    data={"chat_id": self.chat_id, "text": text},
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram_send_failed", error=str(exc))
            return False


class NullAlerter(Alerter):
    async def send(self, message: str, level: str = "info") -> bool:
        log.info("alert", level=level, message=message)
        return True


def build_alerter(env: EnvSettings) -> Alerter:
    if env.telegram_bot_token and env.telegram_chat_id:
        return TelegramAlerter(env.telegram_bot_token, env.telegram_chat_id)
    return NullAlerter()
