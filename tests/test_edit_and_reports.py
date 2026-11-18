from datetime import date
from decimal import Decimal

from bot.handlers import handle_update
from bot.sheets import ExpenseRow
from bot.telegram import TelegramError
from tests.fakes import (
    CHAT_ID,
    FIXED_NOW,
    USER_ID,
    FakeReceipts,
    FakeStore,
    FakeTelegram,
    callback_update,
    make_ctx,
    make_receipt,
    photo_update,
    text_update,
)

ID = f"{CHAT_ID}-10"


def saved(store: FakeStore, tg: FakeTelegram, text: str = "45 spo biedronka") -> None:
    handle_update(text_update(1, text), make_ctx(tg, store))


# --- Zmień kategorię / Anuluj ---


def test_change_shows_category_buttons_then_sets_new_one() -> None:
    tg, store = FakeTelegram(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 spo biedronka"), ctx)

    assert handle_update(callback_update(2, f"e:{ID}"), ctx) == "change_requested"
    edit = tg.edited[-1]
    assert edit["text"].startswith("✏️ Ania · 45,00 zł · Spożywcze i domowe")
    flat = [b for row in edit["reply_markup"]["inline_keyboard"] for b in row]
    assert flat[-1]["callback_data"] == f"a:{ID}"

    assert handle_update(callback_update(3, f"k:{ID}:3"), ctx) == "category_set"
    assert store.rows[0].category == "Samochód"
    assert tg.edited[-1]["text"] == "✅ Ania · 45,00 zł · Samochód · biedronka"


def test_cancel_restores_confirmation() -> None:
    tg, store = FakeTelegram(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 spo biedronka"), ctx)
    assert handle_update(callback_update(2, f"a:{ID}"), ctx) == "change_cancelled"
    assert tg.edited[-1]["text"] == "✅ Ania · 45,00 zł · Spożywcze i domowe · biedronka"
    assert store.rows[0].category == "Spożywcze i domowe"


def test_change_category_of_split_receipt_merges_into_one() -> None:
    tg, store = FakeTelegram(), FakeStore()
    receipts = FakeReceipts(make_receipt((1, "100.00"), (2, "23.45")))
    ctx = make_ctx(tg, store, receipts=receipts)
    handle_update(photo_update(1), ctx)
    handle_update(callback_update(2, f"k:{ID}:4"), ctx)
    assert {r.category for r in store.rows} == {"Mieszkanie i rachunki"}
    assert tg.edited[-1]["text"] == (
        "✅ Ania · Biedronka · 17.11 · 123,45 zł → "
        "Mieszkanie i rachunki 100,00 zł / Mieszkanie i rachunki 23,45 zł"
    )


def test_failed_message_edit_does_not_fail_update() -> None:
    class NotModified(FakeTelegram):
        def edit_message_text(self, *args: object, **kwargs: object) -> None:
            raise TelegramError("message is not modified")

    tg, store = NotModified(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 spo"), ctx)
    assert handle_update(callback_update(2, f"k:{ID}:2"), ctx) == "category_set"
    assert store.rows[0].category == "Odzież i obuwie"


# --- Usuń ---


def test_delete_removes_all_rows_of_entry() -> None:
    tg, store = FakeTelegram(), FakeStore()
    receipts = FakeReceipts(make_receipt((1, "100.00"), (2, "23.45")))
    ctx = make_ctx(tg, store, receipts=receipts)
    handle_update(photo_update(1), ctx)
    handle_update(text_update(5, "10 roz kawa"), ctx)

    assert handle_update(callback_update(6, f"d:{ID}"), ctx) == "deleted"
    assert [r.description for r in store.rows] == ["kawa"]
    assert tg.edited[-1]["text"].startswith("🗑 Usunięto: Ania · Biedronka")
    assert tg.edited[-1]["reply_markup"] is None


def test_delete_twice_reports_missing_row() -> None:
    tg, store = FakeTelegram(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 spo"), ctx)
    handle_update(callback_update(2, f"d:{ID}"), ctx)
    assert handle_update(callback_update(3, f"d:{ID}"), ctx) == "row_missing"
    assert "Nie znalazłem" in tg.edited[-1]["text"]


def test_unknown_action_is_ignored() -> None:
    assert handle_update(callback_update(2, f"x:{ID}"), make_ctx()) == "ignored"


# --- /cofnij ---


def row(expense_id: str, who: str, day: date, category: str, amount: str) -> ExpenseRow:
    return ExpenseRow(
        expense_id=expense_id,
        day=day,
        who=who,
        category=category,
        description="",
        amount=Decimal(amount),
        currency="PLN",
        rate=Decimal(1),
        amount_pln=Decimal(amount),
        source="ręcznie",
        added=FIXED_NOW,
    )


def test_undo_removes_own_last_entry_only() -> None:
    tg, store = FakeTelegram(), FakeStore()
    store.rows = [
        row("a", "Ania", date(2026, 11, 1), "Samochód", "100"),
        row("b", "Ania", date(2026, 11, 2), "Inne", "20"),
        row("c", "Tomek", date(2026, 11, 3), "Inne", "30"),
    ]
    kind = handle_update(text_update(1, "/cofnij"), make_ctx(tg, store))
    assert kind == "undo"
    assert [r.expense_id for r in store.rows] == ["a", "c"]
    assert tg.sent[0]["text"] == "🗑 Usunięto: Ania · 20,00 zł · Inne"


def test_undo_with_nothing_to_remove() -> None:
    tg = FakeTelegram()
    handle_update(text_update(1, "/cofnij"), make_ctx(tg))
    assert tg.sent[0]["text"] == "Nie masz żadnych wpisów do usunięcia."


# --- /suma ---


def test_month_summary_with_limits_and_people() -> None:
    tg, store = FakeTelegram(), FakeStore()
    store.rows = [
        row("a", "Ania", date(2026, 11, 1), "Spożywcze i domowe", "900"),
        row("b", "Tomek", date(2026, 11, 2), "Spożywcze i domowe", "300"),
        row("c", "Ania", date(2026, 11, 3), "Samochód", "1500"),
        row("d", "Ania", date(2026, 10, 30), "Samochód", "999"),
    ]
    store.limit_values = {
        "Spożywcze i domowe": Decimal("1000"),
        "Rozrywka i jedzenie na mieście": Decimal("400"),
    }
    handle_update(text_update(1, "/suma"), make_ctx(tg, store))
    assert tg.sent[0]["text"] == (
        "📊 <b>Listopad 2026</b>: 2 700,00 zł\n"
        "\n"
        "• Spożywcze i domowe: 1 200,00 zł (120% z 1 000,00 zł) ⚠️\n"
        "• Samochód: 1 500,00 zł\n"
        "• Rozrywka i jedzenie na mieście: 0,00 zł (0% z 400,00 zł)\n"
        "\n"
        "Kto: Ania 2 400,00 zł, Tomek 300,00 zł"
    )


def test_month_summary_for_given_month() -> None:
    tg, store = FakeTelegram(), FakeStore()
    store.rows = [row("d", "Ania", date(2026, 10, 30), "Samochód", "999")]
    handle_update(text_update(1, "/suma paź"), make_ctx(tg, store))
    assert tg.sent[0]["text"].startswith("📊 <b>Październik 2026</b>: 999,00 zł")


def test_month_summary_empty_and_bad_month() -> None:
    tg = FakeTelegram()
    ctx = make_ctx(tg)
    handle_update(text_update(1, "/suma"), ctx)
    handle_update(text_update(2, "/suma xyz"), ctx)
    assert tg.sent[0]["text"] == "📊 <b>Listopad 2026</b>: brak wydatków."
    assert tg.sent[1]["text"].startswith("Nie rozumiem miesiąca")


def test_commands_need_sheet() -> None:
    tg = FakeTelegram()
    ctx = make_ctx(tg, with_store=False)
    assert handle_update(text_update(1, "/suma"), ctx) == "no_sheet"
    assert handle_update(text_update(2, "/cofnij", user_id=USER_ID), ctx) == "no_sheet"
