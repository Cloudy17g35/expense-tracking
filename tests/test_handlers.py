from datetime import date, datetime
from decimal import Decimal

from bot.handlers import TZ, handle_update, parse_command
from bot.sheets import UNKNOWN_CATEGORY
from tests.fakes import (
    CHAT_ID,
    FIXED_NOW,
    FakeStore,
    FakeTelegram,
    callback_update,
    make_ctx,
    text_update,
)


def test_parse_command() -> None:
    assert parse_command("/pomoc") == "pomoc"
    assert parse_command("/Pomoc@MojBot jakis argument") == "pomoc"
    assert parse_command("45 spo") is None
    assert parse_command("/") is None


# --- komendy i filtrowanie ---


def test_help_command_replies_in_group() -> None:
    tg = FakeTelegram()
    kind = handle_update(text_update(1, "/pomoc"), make_ctx(tg))
    assert kind == "command"
    assert tg.sent[0]["chat_id"] == CHAT_ID
    assert tg.sent[0]["reply_to"] == 10
    assert "Jak dodać wydatek" in tg.sent[0]["text"]


def test_categories_command_lists_all() -> None:
    tg = FakeTelegram()
    handle_update(text_update(1, "/kategorie"), make_ctx(tg))
    assert "7. Inne" in tg.sent[0]["text"]


def test_foreign_chat_is_ignored() -> None:
    tg, store = FakeTelegram(), FakeStore()
    kind = handle_update(text_update(1, "45 spo", chat_id=-999), make_ctx(tg, store))
    assert kind == "foreign_chat"
    assert tg.sent == [] and store.rows == []


def test_unknown_user_is_ignored() -> None:
    tg, store = FakeTelegram(), FakeStore()
    kind = handle_update(text_update(1, "45 spo", user_id=222), make_ctx(tg, store))
    assert kind == "unknown_user"
    assert tg.sent == [] and store.rows == []


def test_update_without_message_is_ignored() -> None:
    assert handle_update({"update_id": 1}, make_ctx()) == "ignored"


def test_conversation_is_ignored() -> None:
    tg, store = FakeTelegram(), FakeStore()
    assert handle_update(text_update(1, "kupiłem 2 bułki"), make_ctx(tg, store)) == "ignored"
    assert tg.sent == [] and store.rows == []


# --- wpisy „z palca” ---


def test_manual_expense_is_saved_and_confirmed() -> None:
    tg, store = FakeTelegram(), FakeStore()
    kind = handle_update(text_update(4, "45,50 spo biedronka"), make_ctx(tg, store))
    assert kind == "expense"

    [row] = store.rows
    assert row.expense_id == f"{CHAT_ID}-40"
    assert row.day == date(2026, 11, 18)
    assert row.who == "Ania"
    assert row.category == "Spożywcze i domowe"
    assert row.description == "biedronka"
    assert row.amount == Decimal("45.50")
    assert row.currency == "PLN"
    assert row.rate == 1
    assert row.amount_pln == Decimal("45.50")
    assert row.source == "ręcznie"
    assert row.added == FIXED_NOW

    assert tg.sent[0]["text"] == "✅ Ania · 45,50 zł · Spożywcze i domowe · biedronka"
    assert tg.sent[0]["reply_to"] == 40
    assert tg.sent[0]["reply_markup"] is None


def test_foreign_currency_is_converted() -> None:
    tg, store = FakeTelegram(), FakeStore()
    handle_update(text_update(1, "20 eur roz kawa"), make_ctx(tg, store))
    [row] = store.rows
    assert row.currency == "EUR"
    assert row.rate == Decimal("4.2345")
    assert row.amount_pln == Decimal("84.69")
    assert "20,00 € (84,69 zł)" in tg.sent[0]["text"]


def test_expense_date_is_send_date_in_polish_time() -> None:
    # 00:30 18.11 czasu polskiego to jeszcze 17.11 w UTC. Liczy się data polska.
    late = int(datetime(2026, 11, 18, 0, 30, tzinfo=TZ).timestamp())
    store = FakeStore()
    handle_update(text_update(1, "10 spo", date=late), make_ctx(store=store))
    assert store.rows[0].day == date(2026, 11, 18)


def test_duplicate_is_skipped() -> None:
    tg, store = FakeTelegram(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "10 spo"), ctx)
    assert handle_update(text_update(1, "10 spo"), ctx) == "duplicate"
    assert len(store.rows) == 1
    assert len(tg.sent) == 1


def test_without_sheet_bot_says_so() -> None:
    tg = FakeTelegram()
    kind = handle_update(text_update(1, "10 spo"), make_ctx(tg, with_store=False))
    assert kind == "no_sheet"
    assert "nie jest jeszcze podłączony" in tg.sent[0]["text"]


def test_html_in_description_is_escaped() -> None:
    tg = FakeTelegram()
    handle_update(text_update(1, "10 spo <b>x</b>"), make_ctx(tg))
    assert "&lt;b&gt;x&lt;/b&gt;" in tg.sent[0]["text"]


# --- brak kategorii i przyciski ---


def test_missing_category_asks_with_buttons() -> None:
    tg, store = FakeTelegram(), FakeStore()
    kind = handle_update(text_update(1, "45 biedronka"), make_ctx(tg, store))
    assert kind == "expense_needs_category"
    assert store.rows[0].category == UNKNOWN_CATEGORY

    message = tg.sent[0]
    assert message["text"] == "❓ Ania · 45,00 zł · biedronka\nWybierz kategorię:"
    buttons = [b for row in message["reply_markup"]["inline_keyboard"] for b in row]
    assert len(buttons) == 7
    assert buttons[0]["callback_data"] == f"k:{CHAT_ID}-10:1"
    assert all(len(b["callback_data"].encode()) <= 64 for b in buttons)


def test_button_sets_category_and_edits_message() -> None:
    tg, store = FakeTelegram(), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 biedronka"), ctx)
    kind = handle_update(callback_update(2, f"k:{CHAT_ID}-10:1"), ctx)
    assert kind == "category_set"
    assert store.rows[0].category == "Spożywcze i domowe"
    assert tg.edited == [
        {
            "chat_id": CHAT_ID,
            "message_id": 999,
            "text": "✅ Ania · 45,00 zł · biedronka · Spożywcze i domowe",
        }
    ]
    assert tg.answered == ["cq2"]


def test_stale_button_answer_does_not_fail() -> None:
    tg, store = FakeTelegram(stale_callbacks=True), FakeStore()
    ctx = make_ctx(tg, store)
    handle_update(text_update(1, "45 biedronka"), ctx)
    assert handle_update(callback_update(2, f"k:{CHAT_ID}-10:3"), ctx) == "category_set"
    assert store.rows[0].category == "Samochód"


def test_button_from_foreign_chat_is_ignored() -> None:
    store = FakeStore()
    ctx = make_ctx(store=store)
    handle_update(text_update(1, "45 biedronka"), ctx)
    kind = handle_update(callback_update(2, f"k:{CHAT_ID}-10:1", chat_id=-5), ctx)
    assert kind == "foreign_chat"
    assert store.rows[0].category == UNKNOWN_CATEGORY


def test_malformed_button_data_is_ignored() -> None:
    tg = FakeTelegram()
    for data in ["", "k", "k:x:9", "z:1:1", "k::1"]:
        assert handle_update(callback_update(2, data), make_ctx(tg)) == "ignored"
