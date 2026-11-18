from typing import Any

from bot.config import Settings
from bot.telegram import Update

CHAT_ID = -1001
USER_ID = 111


def make_settings() -> Settings:
    return Settings(
        telegram_token="test-token",  # type: ignore[arg-type]
        allowed_chat_id=CHAT_ID,
        users={USER_ID: "Ania"},
    )


def text_update(
    update_id: int, text: str, chat_id: int = CHAT_ID, user_id: int = USER_ID
) -> Update:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": 1_794_989_780,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": user_id, "is_bot": False, "first_name": "X"},
            "text": text,
        },
    }


class FakeTelegram:
    """Zachowuje się jak getUpdates: offset potwierdza wcześniejsze aktualizacje."""

    def __init__(self, updates: list[Update]) -> None:
        self.pending = list(updates)
        self.sent: list[dict[str, Any]] = []
        self.offsets: list[int | None] = []

    def get_updates(self, offset: int | None) -> list[Update]:
        self.offsets.append(offset)
        if offset is not None:
            self.pending = [u for u in self.pending if u["update_id"] >= offset]
        return list(self.pending)

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_to": reply_to, "reply_markup": reply_markup}
        )
        return {"message_id": 999}
