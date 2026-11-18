"""Obsługa pojedynczej aktualizacji z Telegrama."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from bot.categories import CATEGORIES, by_number
from bot.config import Settings
from bot.fx import FxError, RateProvider
from bot.money import BASE_CURRENCY, format_amount, round2
from bot.parse import ParsedExpense, parse_expense, scan
from bot.receipt import IMAGE_TYPES, Receipt, ReceiptReader, ReceiptSplit
from bot.sheets import UNKNOWN_CATEGORY, ExpenseRow, ExpenseStore, rows_for
from bot.summary import month_summary, parse_month
from bot.telegram import TelegramAPI, TelegramError, Update

log = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Warsaw")
SOURCE_MANUAL = "ręcznie"
SOURCE_PHOTO = "zdjęcie"
# Data z paragonu jest brana, jeśli nie jest późniejsza niż wiadomość i nie starsza niż tyle dni.
MAX_RECEIPT_AGE_DAYS = 60

# Przyciski: <akcja>:<ID wpisu>[:<numer kategorii>]
CB_SET_CATEGORY = "k"
CB_CHANGE = "e"
CB_DELETE = "d"
CB_CANCEL = "a"

HELP_TEXT = """<b>Jak dodać wydatek</b>

<b>Z palca:</b> <code>kwota [waluta] kategoria [opis]</code>
<code>45,50 spo biedronka</code>
<code>1500 sam rata leasingu</code>
<code>20 eur roz kawa w Wiedniu</code>
<code>350 czk sam parking Praga</code>

Waluta: domyślnie zł, można też <code>eur</code> i <code>czk</code>.
Bez kategorii zapytam przyciskami.

<b>Zdjęcie paragonu:</b> po prostu wyślij zdjęcie. W podpisie możesz wymusić kategorię lub walutę.

<b>Poprawki:</b> pod każdym wpisem są przyciski „Zmień kategorię” i „Usuń”.

<b>Komendy:</b>
/suma: wydatki w bieżącym miesiącu (albo np. <code>/suma paź</code>, <code>/suma 2026-10</code>)
/cofnij: usuwa Twój ostatni wpis
/kategorie: lista kategorii i skrótów

Bot sprawdza wiadomości co kilka minut, więc odpowiedź może chwilę potrwać."""

NO_SHEET_TEXT = "Arkusz nie jest jeszcze podłączony, więc nie zapisałem tego wydatku."
NO_SHEET_SHORT = "Arkusz nie jest jeszcze podłączony."
NO_READER_TEXT = (
    "Odczyt zdjęć nie jest jeszcze włączony. Wpisz wydatek ręcznie, np. <code>123,45 spo</code>."
)
UNREADABLE_TEXT = (
    "Nie odczytałem tego paragonu. Wpisz wydatek ręcznie, np. <code>123,45 spo biedronka</code>."
)
BAD_MONTH_TEXT = (
    "Nie rozumiem miesiąca. Przykłady: <code>/suma</code>, <code>/suma paź</code>, "
    "<code>/suma 2026-10</code>."
)
NOTHING_TO_UNDO_TEXT = "Nie masz żadnych wpisów do usunięcia."
MISSING_ROW_TEXT = "Nie znalazłem tego wpisu w arkuszu (może został już usunięty)."


def _now() -> datetime:
    return datetime.now(TZ)


@dataclass
class Context:
    settings: Settings
    tg: TelegramAPI
    store: ExpenseStore | None
    fx: RateProvider
    receipts: ReceiptReader | None = None
    now: Callable[[], datetime] = field(default=_now)


# --- teksty i klawiatury ---


def categories_text() -> str:
    lines = ["<b>Kategorie</b> (numer albo skrót):"]
    for c in CATEGORIES:
        aliases = ", ".join(f"<code>{a}</code>" for a in c.aliases)
        lines.append(f"{c.number}. {escape(c.name)}: {aliases}")
    return "\n".join(lines)


def category_keyboard(expense_id: str, with_cancel: bool = False) -> dict[str, Any]:
    buttons = [
        {"text": c.name, "callback_data": f"{CB_SET_CATEGORY}:{expense_id}:{c.number}"}
        for c in CATEGORIES
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    if with_cancel:
        rows[-1].append({"text": "Anuluj", "callback_data": f"{CB_CANCEL}:{expense_id}"})
    return {"inline_keyboard": rows}


def action_keyboard(expense_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Zmień kategorię", "callback_data": f"{CB_CHANGE}:{expense_id}"},
                {"text": "Usuń", "callback_data": f"{CB_DELETE}:{expense_id}"},
            ]
        ]
    }


def describe(rows: list[ExpenseRow]) -> str:
    """Opis wpisu (bez znaczka na początku), np. 'Ania · 45,50 zł · Spożywcze… · biedronka'."""
    first = rows[0]
    currency = first.currency
    total = sum((r.amount for r in rows), Decimal(0))
    amount_text = format_amount(total, currency)
    if currency != BASE_CURRENCY:
        total_pln = sum((r.amount_pln for r in rows), Decimal(0))
        amount_text += f" ({format_amount(total_pln)})"

    if first.source == SOURCE_PHOTO:
        head = [escape(first.who)]
        if first.description:
            head.append(escape(first.description))
        head += [first.day.strftime("%d.%m"), amount_text]
        splits = " / ".join(
            f"{escape(r.category)} {format_amount(r.amount, currency)}" for r in rows
        )
        return f"{' · '.join(head)} → {splits}"

    parts = [escape(first.who), amount_text, escape(first.category)]
    if first.description:
        parts.append(escape(first.description))
    return " · ".join(parts)


def question_text(row: ExpenseRow) -> str:
    amount_text = format_amount(row.amount, row.currency)
    if row.currency != BASE_CURRENCY:
        amount_text += f" ({format_amount(row.amount_pln)})"
    parts = [escape(row.who), amount_text]
    if row.description:
        parts.append(escape(row.description))
    return "❓ " + " · ".join(parts) + "\nWybierz kategorię:"


def parse_command(text: str) -> tuple[str, str] | None:
    """'/suma@MojBot paź' -> ('suma', 'paź'). Zwraca None, jeśli to nie komenda."""
    if not text.startswith("/"):
        return None
    head, _, arg = text.partition(" ")
    name = head[1:].split("@", 1)[0].lower()
    return (name, arg.strip()) if name else None


# --- routing ---


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
    who = ctx.settings.users[user_id]

    if _image_file(message):
        return _save_receipt(message, who, ctx)

    text: str = message.get("text") or ""
    if command := parse_command(text):
        return _handle_command(*command, message, who, ctx)

    parsed = parse_expense(text)
    if parsed is None:
        return "ignored"
    return _save_manual_expense(message, parsed, who, ctx)


def _handle_command(name: str, arg: str, message: dict[str, Any], who: str, ctx: Context) -> str:
    chat_id: int = message["chat"]["id"]
    message_id: int = message["message_id"]

    def reply(text: str) -> None:
        ctx.tg.send_message(chat_id, text, reply_to=message_id)

    if name in ("pomoc", "help", "start"):
        reply(HELP_TEXT)
    elif name == "kategorie":
        reply(categories_text())
    elif name == "suma":
        if ctx.store is None:
            reply(NO_SHEET_SHORT)
            return "no_sheet"
        month = parse_month(arg, ctx.now().date())
        if month is None:
            reply(BAD_MONTH_TEXT)
        else:
            reply(month_summary(ctx.store.all_rows(), *month, ctx.store.limits()))
    elif name == "cofnij":
        if ctx.store is None:
            reply(NO_SHEET_SHORT)
            return "no_sheet"
        return _undo_last(who, reply, ctx.store)
    else:
        return "ignored"
    return "command"


def _undo_last(who: str, reply: Callable[[str], None], store: ExpenseStore) -> str:
    rows = store.all_rows()
    mine = [r for r in rows if r.who == who]
    if not mine:
        reply(NOTHING_TO_UNDO_TEXT)
        return "command"
    # Wiersze są w kolejności dopisywania, więc ostatni jest najnowszy.
    expense_id = mine[-1].expense_id
    removed = [r for r in rows if r.expense_id == expense_id]
    store.delete(expense_id)
    reply(f"🗑 Usunięto: {describe(removed)}")
    return "undo"


# --- wpisy „z palca” ---


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
    row = ExpenseRow(
        expense_id=expense_id,
        day=day,
        who=who,
        category=parsed.category.name if parsed.category else UNKNOWN_CATEGORY,
        description=parsed.description,
        amount=parsed.amount,
        currency=parsed.currency,
        rate=rate,
        amount_pln=round2(parsed.amount * rate),
        source=SOURCE_MANUAL,
        added=ctx.now(),
    )
    ctx.store.append([row])

    if parsed.category is None:
        ctx.tg.send_message(
            chat_id,
            question_text(row),
            reply_to=message_id,
            reply_markup=category_keyboard(expense_id),
        )
        return "expense_needs_category"

    ctx.tg.send_message(
        chat_id,
        f"✅ {describe([row])}",
        reply_to=message_id,
        reply_markup=action_keyboard(expense_id),
    )
    return "expense"


# --- zdjęcia paragonów ---


def _image_file(message: dict[str, Any]) -> tuple[str, str] | None:
    """(file_id, typ MIME) zdjęcia albo obrazu wysłanego jako plik."""
    if photos := message.get("photo"):
        # Telegram podaje kilka rozmiarów; największy jest ostatni. Zdjęcia są w JPEG.
        largest = max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))
        return largest["file_id"], "image/jpeg"
    document = message.get("document") or {}
    if document.get("mime_type") in IMAGE_TYPES:
        return document["file_id"], document["mime_type"]
    return None


def _save_receipt(message: dict[str, Any], who: str, ctx: Context) -> str:
    chat_id: int = message["chat"]["id"]
    message_id: int = message["message_id"]
    if ctx.store is None:
        ctx.tg.send_message(chat_id, NO_SHEET_TEXT, reply_to=message_id)
        return "no_sheet"
    if ctx.receipts is None:
        ctx.tg.send_message(chat_id, NO_READER_TEXT, reply_to=message_id)
        return "no_reader"

    expense_id = f"{chat_id}-{message_id}"
    if ctx.store.has_id(expense_id):
        return "duplicate"

    image = _image_file(message)
    assert image is not None
    file_id, media_type = image
    receipt = ctx.receipts.read(ctx.tg.download_file(file_id), media_type)
    if receipt is None:
        ctx.tg.send_message(chat_id, UNREADABLE_TEXT, reply_to=message_id)
        return "receipt_unreadable"

    receipt = _apply_caption(receipt, message.get("caption") or "")
    sent_day = datetime.fromtimestamp(message["date"], TZ).date()
    day = sent_day
    if receipt.day and 0 <= (sent_day - receipt.day).days <= MAX_RECEIPT_AGE_DAYS:
        day = receipt.day

    try:
        rate = ctx.fx.rate(receipt.currency, day)
    except FxError:
        # Nieznana waluta: ponawianie nic nie da.
        ctx.tg.send_message(chat_id, UNREADABLE_TEXT, reply_to=message_id)
        return "receipt_unknown_currency"

    added = ctx.now()
    rows = [
        ExpenseRow(
            expense_id=expense_id,
            day=day,
            who=who,
            category=split.category.name,
            description=receipt.merchant,
            amount=split.amount,
            currency=receipt.currency,
            rate=rate,
            amount_pln=round2(split.amount * rate),
            source=SOURCE_PHOTO,
            added=added,
        )
        for split in receipt.splits
    ]
    ctx.store.append(rows)
    ctx.tg.send_message(
        chat_id,
        f"✅ {describe(rows)}",
        reply_to=message_id,
        reply_markup=action_keyboard(expense_id),
    )
    return "receipt"


def _apply_caption(receipt: Receipt, caption: str) -> Receipt:
    """Podpis pod zdjęciem nadpisuje odczyt: kwotę, walutę, kategorię, opis."""
    if not caption.strip():
        return receipt
    found = scan(caption)
    total = found.amount if found.amount and found.amount > 0 else receipt.total
    splits = receipt.splits
    if found.category is not None:
        splits = (ReceiptSplit(found.category, total),)
    elif total != receipt.total:
        # Inna kwota niż odczytana: całość do głównej kategorii z paragonu.
        splits = (ReceiptSplit(receipt.splits[0].category, total),)
    merchant = " ".join(p for p in (receipt.merchant, found.description) if p)
    return Receipt(
        merchant=merchant,
        day=receipt.day,
        total=total,
        currency=found.currency or receipt.currency,
        splits=splits,
    )


# --- przyciski ---


def _handle_callback(query: dict[str, Any], ctx: Context) -> str:
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    if chat_id != ctx.settings.allowed_chat_id:
        return "foreign_chat"
    if query.get("from", {}).get("id") not in ctx.settings.users:
        return "unknown_user"

    action, _, rest = (query.get("data") or "").partition(":")
    if action == CB_SET_CATEGORY:
        expense_id, _, number = rest.rpartition(":")
    else:
        expense_id, number = rest, ""
    if not expense_id or action not in (CB_SET_CATEGORY, CB_CHANGE, CB_DELETE, CB_CANCEL):
        _answer(ctx, query["id"])
        return "ignored"
    category = by_number(int(number)) if number.isdigit() else None
    if (action == CB_SET_CATEGORY and category is None) or ctx.store is None:
        _answer(ctx, query["id"])
        return "ignored"

    message_id: int = message["message_id"]

    def edit(text: str, markup: dict[str, Any] | None = None) -> None:
        # Arkusz jest już zmieniony; nieudana edycja wiadomości (np. „message is not
        # modified” po podwójnym kliknięciu albo zbyt stara wiadomość) nie może blokować kolejki.
        try:
            ctx.tg.edit_message_text(chat_id, message_id, text, reply_markup=markup)
        except TelegramError as error:
            log.info("Nie zmieniono wiadomości bota: %s", error)

    if action == CB_DELETE:
        rows = rows_for(ctx.store, expense_id)
        if not rows:
            edit(MISSING_ROW_TEXT)
            _answer(ctx, query["id"])
            return "row_missing"
        ctx.store.delete(expense_id)
        edit(f"🗑 Usunięto: {describe(rows)}")
        _answer(ctx, query["id"], "Usunięto")
        return "deleted"

    if action == CB_SET_CATEGORY:
        assert category is not None
        ctx.store.set_category(expense_id, category.name)

    rows = rows_for(ctx.store, expense_id)
    if not rows:
        edit(MISSING_ROW_TEXT)
        _answer(ctx, query["id"])
        return "row_missing"

    if action == CB_CHANGE:
        edit(f"✏️ {describe(rows)}\nWybierz nową kategorię:", category_keyboard(expense_id, True))
        _answer(ctx, query["id"])
        return "change_requested"

    # Ustawiona kategoria albo „Anuluj”: zwykłe potwierdzenie z przyciskami.
    edit(f"✅ {describe(rows)}", action_keyboard(expense_id))
    _answer(ctx, query["id"], category.name if category else None)
    return "category_set" if category else "change_cancelled"


def _answer(ctx: Context, query_id: str, text: str | None = None) -> None:
    # Bot odpowiada z opóźnieniem, więc Telegram często odrzuca już „przeterminowane” zapytanie.
    try:
        ctx.tg.answer_callback_query(query_id, text)
    except TelegramError:
        log.info("Pominięto odpowiedź na przycisk (zbyt stare zapytanie)")
