"""Minimalny klient Telegram Bot API (tylko to, czego bot potrzebuje)."""

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

# Chwilowe problemy z siecią lub Telegramem: ponawiamy kilka razy, zanim uruchomienie
# się wywróci (wtedy wiadomość i tak wróci w następnym uruchomieniu).
ATTEMPTS = 4
BACKOFF_SECONDS = (2, 5, 10)
MAX_RETRY_AFTER = 30

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

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None: ...

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...

    def download_file(self, file_id: str) -> bytes: ...


class TelegramClient:
    ALLOWED_UPDATES = ("message", "callback_query")

    def __init__(
        self,
        token: str,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._file_base = f"https://api.telegram.org/file/bot{token}"
        self._http = http or httpx.Client(timeout=httpx.Timeout(30, connect=10))
        self._sleep = sleep

    def _send(self, name: str, request: Callable[[], httpx.Response]) -> httpx.Response:
        """Wysyła zapytanie, ponawiając przy timeoutach, błędach sieci, 429 i 5xx."""
        for attempt in range(ATTEMPTS):
            last = attempt == ATTEMPTS - 1
            try:
                response = request()
            except httpx.TransportError as error:
                if last:
                    raise
                # Nazwa typu wystarczy; komunikat httpx może zawierać URL z tokenem.
                log.warning("%s: %s, ponawiam", name, type(error).__name__)
                self._sleep(BACKOFF_SECONDS[attempt])
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if last:
                    return response
                delay: float = BACKOFF_SECONDS[attempt]
                if response.status_code == 429:
                    retry_after = _retry_after(response)
                    delay = min(retry_after, MAX_RETRY_AFTER) if retry_after else delay
                log.warning("%s: HTTP %s, ponawiam", name, response.status_code)
                self._sleep(delay)
                continue
            return response
        raise AssertionError("unreachable")

    def _call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        response = self._send(
            method, lambda: self._http.post(f"{self._base}/{method}", json=payload)
        )
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

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Zmienia treść wiadomości bota. Bez reply_markup usuwa przyciski."""
        self._call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    def download_file(self, file_id: str) -> bytes:
        """Pobiera plik (np. zdjęcie). Boty mogą pobierać pliki do 20 MB."""
        info = self._call("getFile", file_id=file_id)
        url = f"{self._file_base}/{info['file_path']}"
        response = self._send("download", lambda: self._http.get(url, timeout=60))
        if response.status_code != 200:
            raise TelegramError(f"download: HTTP {response.status_code}")
        return response.content


def _retry_after(response: httpx.Response) -> float | None:
    try:
        value = response.json().get("parameters", {}).get("retry_after")
    except ValueError:
        return None
    return float(value) if isinstance(value, int | float) else None
