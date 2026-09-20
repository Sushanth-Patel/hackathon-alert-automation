"""Telegram bot notifier with exponential backoff and message chunking support."""

from __future__ import annotations
import os
import time
import logging
from typing import Union, List
import requests
from notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(BaseNotifier):
    """Notifier delivering HTML digests to a Telegram chat via Bot API."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ):
        super().__init__(name="telegram", enabled=enabled)
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def send(self, content: Union[str, List[str]]) -> bool:
        """Send message or list of message chunks sequentially."""
        if not self.enabled:
            logger.info("Telegram notifier is disabled in config.")
            return True

        if not self.token or not self.chat_id:
            logger.error("Telegram notifier enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing!")
            return False

        chunks = [content] if isinstance(content, str) else content
        if not chunks:
            logger.info("No content to send to Telegram.")
            return True

        all_success = True
        for idx, chunk in enumerate(chunks):
            success = self._send_chunk_with_retry(chunk)
            if not success:
                all_success = False
                logger.error("Failed to send chunk %d of %d to Telegram", idx + 1, len(chunks))
            time.sleep(1.0)  # Gentle pause between successive chunks to avoid hitting Telegram's rate limit

        return all_success

    def _send_chunk_with_retry(self, chunk: str) -> bool:
        url = TELEGRAM_API_URL.format(token=self.token)
        payload = {
            "chat_id": self.chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                if resp.status_code == 200 and resp.json().get("ok"):
                    logger.info("Successfully sent message to Telegram (attempt %d)", attempt)
                    return True

                if resp.status_code == 429:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", delay)
                    logger.warning("Telegram rate limit hit. Waiting %s seconds...", retry_after)
                    time.sleep(float(retry_after))
                    continue

                logger.warning(
                    "Telegram API returned %d: %s (attempt %d/%d)",
                    resp.status_code,
                    resp.text,
                    attempt,
                    self.max_retries,
                )
            except Exception as e:
                logger.warning("Error posting to Telegram (attempt %d/%d): %s", attempt, self.max_retries, e)

            if attempt < self.max_retries:
                time.sleep(delay)
                delay *= self.backoff_factor

        return False
