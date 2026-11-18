from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from bot.config import Settings
from bot.handlers import TZ, Context
from bot.sheets import ExpenseRow
from bot.telegram import TelegramError, Update

CHAT_ID = -1001
USER_ID = 111
# 2026-11-18 10:00 czasu polskiego
MESSAGE_DATE = int(datetime(2026, 11, 18, 10, 0, tzinfo=TZ).timestamp())


def make_settings() -> Settings:
    return Settings(
        telegram_token="test-token",  # type: ignore[arg-type]
        allowed_chat_id=CHAT_ID,
        users={USER_ID: "Ania"},
    )


def text_update(
    update_id: int,
    text: str,
    chat_id: int = CHAT_ID,
    user_id: int = USER_ID,
    date: int = MESSAGE_DATE,
) -> Update:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": date,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": user_id, "is_bot": False, "first_name": "X"},
            "text": text,
        },
    }


def callback_update(
    update_id: int,
    data: str,
    message_text: str = "❓ Ania · 45,00 zł · biedronka\nWybierz kategorię:",
    chat_id: int = CHAT_ID,
    user_id: int = USER_ID,
) -> Update:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cq{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "X"},
            "message": {
                "message_id": 999,
                "chat": {"id": chat_id, "type": "supergroup"},
                "text": message_text,
            },
            "data": data,
        },
    }


class FakeTelegram:
    """Zachowuje się jak getUpdates: offset potwierdza wcześniejsze aktualizacje."""

    def __init__(self, updates: list[Update] | None = None, stale_callbacks: bool = False) -> None:
        self.pending = list(updates or [])
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.answered: list[str] = []
        self.offsets: list[int | None] = []
        self.stale_callbacks = stale_callbacks

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

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        if self.stale_callbacks:
            raise TelegramError("query is too old")
        self.answered.append(callback_query_id)


class FakeStore:
    def __init__(self) -> None:
        self.rows: list[ExpenseRow] = []

    def has_id(self, expense_id: str) -> bool:
        return any(r.expense_id == expense_id for r in self.rows)

    def append(self, rows: list[ExpenseRow]) -> None:
        self.rows.extend(rows)

    def set_category(self, expense_id: str, category: str) -> int:
        count = 0
        for i, row in enumerate(self.rows):
            if row.expense_id == expense_id:
                self.rows[i] = replace(row, category=category)
                count += 1
        return count


class FakeRates:
    RATES: ClassVar[dict[str, Decimal]] = {
        "PLN": Decimal(1),
        "EUR": Decimal("4.2345"),
        "CZK": Decimal("0.1807"),
    }

    def __init__(self) -> None:
        self.calls: list[tuple[str, date]] = []

    def rate(self, currency: str, day: date) -> Decimal:
        self.calls.append((currency, day))
        return self.RATES[currency]


FIXED_NOW = datetime(2026, 11, 18, 10, 5, tzinfo=TZ)


def make_ctx(
    tg: FakeTelegram | None = None, store: FakeStore | None = None, with_store: bool = True
) -> Context:
    return Context(
        settings=make_settings(),
        tg=tg or FakeTelegram(),
        store=(store or FakeStore()) if with_store else None,
        fx=FakeRates(),
        now=lambda: FIXED_NOW,
    )
