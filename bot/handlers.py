"""Obsługa pojedynczej aktualizacji z Telegrama."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from bot.categories import CATEGORIES, by_number
from bot.config import Settings
from bot.fx import RateProvider
from bot.money import BASE_CURRENCY, format_amount, round2
from bot.parse import ParsedExpense, parse_expense
from bot.sheets import UNKNOWN_CATEGORY, ExpenseRow, ExpenseStore
from bot.telegram import TelegramAPI, TelegramError, Update

log = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Warsaw")
SOURCE_MANUAL = "ręcznie"
CALLBACK_CATEGORY = "k"

HELP_TEXT = """<b>Jak dodać wydatek</b>

<b>Z palca:</b> <code>kwota [waluta] kategoria [opis]</code>
<code>45,50 spo biedronka</code>
<code>1500 sam rata leasingu</code>
<code>20 eur roz kawa w Wiedniu</code>
<code>350 czk sam parking Praga</code>

Waluta: domyślnie zł, można też <code>eur</code> i <code>czk</code>.
Bez kategorii zapytam przyciskami.

<b>Zdjęcie paragonu:</b> po prostu wyślij zdjęcie. W podpisie możesz wymusić kategorię lub walutę.

<b>Komendy:</b> /suma, /cofnij, /kategorie, /pomoc

Bot sprawdza wiadomości co kilka minut, więc odpowiedź może chwilę potrwać."""

NO_SHEET_TEXT = "Arkusz nie jest jeszcze podłączony, więc nie zapisałem tego wydatku."


def _now() -> datetime:
    return datetime.now(TZ)


@dataclass
class Context:
    settings: Settings
    tg: TelegramAPI
    store: ExpenseStore | None
    fx: RateProvider
    now: Callable[[], datetime] = field(default=_now)


def categories_text() -> str:
    lines = ["<b>Kategorie</b> (numer albo skrót):"]
    for c in CATEGORIES:
        aliases = ", ".join(f"<code>{a}</code>" for a in c.aliases)
        lines.append(f"{c.number}. {escape(c.name)}: {aliases}")
    return "\n".join(lines)


def category_keyboard(expense_id: str) -> dict[str, Any]:
    buttons = [
        {"text": c.name, "callback_data": f"{CALLBACK_CATEGORY}:{expense_id}:{c.number}"}
        for c in CATEGORIES
    ]
    return {"inline_keyboard": [buttons[i : i + 2] for i in range(0, len(buttons), 2)]}


def parse_command(text: str) -> str | None:
    """'/pomoc@MojBot arg' -> 'pomoc'. Zwraca None, jeśli to nie komenda."""
    if not text.startswith("/"):
        return None
    head = text.split(maxsplit=1)[0][1:]
    return head.split("@", 1)[0].lower() or None


def handle_update(update: Update, ctx: Context) -> str:
    """Przetwarza aktualizację i zwraca jej rodzaj (do liczników w logach)."""
    if "callback_query" in update:
        return _handle_callback(update["callback_query"], ctx)
    message = update.get("message")
    if not message:
        return "ignored"

    chat_id = message.get("chat", {}).get("id")
    if chat_id != ctx.settings.allowed_chat_id:
        return "foreign_chat"
    user_id = message.get("from", {}).get("id")
    if user_id not in ctx.settings.users:
        return "unknown_user"

    text: str = message.get("text") or ""
    command = parse_command(text)
    if command in ("pomoc", "help", "start"):
        ctx.tg.send_message(chat_id, HELP_TEXT, reply_to=message["message_id"])
        return "command"
    if command == "kategorie":
        ctx.tg.send_message(chat_id, categories_text(), reply_to=message["message_id"])
        return "command"

    parsed = parse_expense(text)
    if parsed is None:
        return "ignored"
    return _save_manual_expense(message, parsed, ctx.settings.users[user_id], ctx)


def _save_manual_expense(
    message: dict[str, Any], parsed: ParsedExpense, who: str, ctx: Context
) -> str:
    chat_id: int = message["chat"]["id"]
    message_id: int = message["message_id"]
    if ctx.store is None:
        ctx.tg.send_message(chat_id, NO_SHEET_TEXT, reply_to=message_id)
        return "no_sheet"

    expense_id = f"{chat_id}-{message_id}"
    if ctx.store.has_id(expense_id):
        # Już zapisany w poprzednim, przerwanym uruchomieniu.
        return "duplicate"

    # Data wydatku to moment wysłania wiadomości, a nie przetworzenia przez bota.
    day = datetime.fromtimestamp(message["date"], TZ).date()
    rate = ctx.fx.rate(parsed.currency, day)
    amount_pln = round2(parsed.amount * rate)
    category = parsed.category.name if parsed.category else UNKNOWN_CATEGORY

    ctx.store.append(
        [
            ExpenseRow(
                expense_id=expense_id,
                day=day,
                who=who,
                category=category,
                description=parsed.description,
                amount=parsed.amount,
                currency=parsed.currency,
                rate=rate,
                amount_pln=amount_pln,
                source=SOURCE_MANUAL,
                added=ctx.now(),
            )
        ]
    )

    amount_text = format_amount(parsed.amount, parsed.currency)
    if parsed.currency != BASE_CURRENCY:
        amount_text += f" ({format_amount(amount_pln)})"
    parts = [escape(who), amount_text]
    parts_tail = [escape(parsed.description)] if parsed.description else []

    if parsed.category is None:
        text = "❓ " + " · ".join(parts + parts_tail) + "\nWybierz kategorię:"
        ctx.tg.send_message(
            chat_id, text, reply_to=message_id, reply_markup=category_keyboard(expense_id)
        )
        return "expense_needs_category"

    text = "✅ " + " · ".join([*parts, escape(category), *parts_tail])
    ctx.tg.send_message(chat_id, text, reply_to=message_id)
    return "expense"


def _handle_callback(query: dict[str, Any], ctx: Context) -> str:
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    if chat_id != ctx.settings.allowed_chat_id:
        return "foreign_chat"
    if query.get("from", {}).get("id") not in ctx.settings.users:
        return "unknown_user"

    kind, _, rest = (query.get("data") or "").partition(":")
    expense_id, _, number = rest.rpartition(":")
    category = by_number(int(number)) if number.isdigit() else None
    if kind != CALLBACK_CATEGORY or not expense_id or category is None or ctx.store is None:
        _answer(ctx, query["id"])
        return "ignored"

    updated = ctx.store.set_category(expense_id, category.name)
    if updated:
        # Telegram zwraca treść bez znaczników HTML, więc escapujemy ją ponownie.
        first_line = (message.get("text") or "").split("\n", 1)[0].removeprefix("❓ ")
        text = f"✅ {escape(first_line)} · {escape(category.name)}"
        ctx.tg.edit_message_text(chat_id, message["message_id"], text)
    _answer(ctx, query["id"], category.name if updated else "Nie znalazłem wpisu w arkuszu")
    return "category_set" if updated else "category_missing_row"


def _answer(ctx: Context, query_id: str, text: str | None = None) -> None:
    # Bot odpowiada z opóźnieniem, więc Telegram często odrzuca już „przeterminowane” zapytanie.
    try:
        ctx.tg.answer_callback_query(query_id, text)
    except TelegramError:
        log.info("Pominięto odpowiedź na przycisk (zbyt stare zapytanie)")
