"""Minimalny klient Telegram Bot API (tylko to, czego bot potrzebuje)."""

from typing import Any, Protocol

import httpx

Update = dict[str, Any]


class TelegramError(RuntimeError):
    pass


class TelegramAPI(Protocol):
    def get_updates(self, offset: int | None) -> list[Update]: ...

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class TelegramClient:
    ALLOWED_UPDATES = ("message", "callback_query")

    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http or httpx.Client(timeout=30)

    def _call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        response = self._http.post(f"{self._base}/{method}", json=payload)
        data = response.json()
        if not data.get("ok"):
            # Nie logujemy URL-a, bo zawiera token.
            raise TelegramError(f"{method}: {data.get('description', response.status_code)}")
        return data["result"]

    def get_updates(self, offset: int | None) -> list[Update]:
        """Pobiera oczekujące aktualizacje. Podanie offsetu potwierdza wszystkie wcześniejsze."""
        result: list[Update] = self._call(
            "getUpdates",
            offset=offset,
            timeout=0,
            limit=100,
            allowed_updates=list(self.ALLOWED_UPDATES),
        )
        return result

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reply_parameters = (
            {"message_id": reply_to, "allow_sending_without_reply": True} if reply_to else None
        )
        result: dict[str, Any] = self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_parameters=reply_parameters,
            reply_markup=reply_markup,
        )
        return result
