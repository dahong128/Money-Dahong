from __future__ import annotations

import httpx


class TelegramNotifier:
    def __init__(self, *, bot_token: str, chat_id: str, timeout_seconds: float = 10.0) -> None:
        self._bot_token = bot_token.strip()
        self._chat_id = chat_id.strip()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(self, text: str) -> None:
        if not self.enabled():
            return
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()

