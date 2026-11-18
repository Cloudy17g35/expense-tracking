from datetime import date, datetime
from decimal import Decimal

from bot.handlers import TZ, handle_update
from tests.fakes import (
    CHAT_ID,
    FakeReceipts,
    FakeStore,
    FakeTelegram,
    make_ctx,
    make_receipt,
    photo_update,
    text_update,
)


def test_receipt_with_split_is_saved_as_rows_with_same_id() -> None:
    tg, store = FakeTelegram(), FakeStore()
    receipts = FakeReceipts(make_receipt((1, "100.00"), (2, "23.45")))
    kind = handle_update(photo_update(3), make_ctx(tg, store, receipts=receipts))

    assert kind == "receipt"
    assert tg.downloaded == ["big"]
    assert receipts.calls == [(b"jpeg-bytes", "image/jpeg")]
    assert [(r.expense_id, r.category, r.amount, r.source) for r in store.rows] == [
        (f"{CHAT_ID}-30", "Spożywcze i domowe", Decimal("100.00"), "zdjęcie"),
        (f"{CHAT_ID}-30", "Odzież i obuwie", Decimal("23.45"), "zdjęcie"),
    ]
    assert all(r.day == date(2026, 11, 17) and r.description == "Biedronka" for r in store.rows)
    assert tg.sent[0]["text"] == (
        "✅ Ania · Biedronka · 17.11 · 123,45 zł → "
        "Spożywcze i domowe 100,00 zł / Odzież i obuwie 23,45 zł"
    )


def test_receipt_in_euro_is_converted() -> None:
    tg, store = FakeTelegram(), FakeStore()
    receipts = FakeReceipts(make_receipt((6, "20.00"), merchant="Café", currency="EUR"))
    handle_update(photo_update(1), make_ctx(tg, store, receipts=receipts))
    assert store.rows[0].amount_pln == Decimal("84.69")
    assert "20,00 € (84,69 zł)" in tg.sent[0]["text"]


def test_caption_category_overrides_split() -> None:
    store = FakeStore()
    receipts = FakeReceipts(make_receipt((1, "100.00"), (2, "23.45")))
    handle_update(photo_update(1, caption="dom"), make_ctx(store=store, receipts=receipts))
    assert [(r.category, r.amount) for r in store.rows] == [
        ("Mieszkanie i rachunki", Decimal("123.45"))
    ]


def test_caption_amount_currency_and_description() -> None:
    store = FakeStore()
    receipts = FakeReceipts(make_receipt((1, "100.00")))
    handle_update(
        photo_update(1, caption="80 eur zakupy na wyjazd"),
        make_ctx(store=store, receipts=receipts),
    )
    [row] = store.rows
    assert (row.amount, row.currency, row.category) == (Decimal("80"), "EUR", "Spożywcze i domowe")
    assert row.description == "Biedronka zakupy na wyjazd"


def test_old_or_future_receipt_date_falls_back_to_message_date() -> None:
    for receipt_day in (date(2026, 1, 1), date(2026, 12, 1), None):
        store = FakeStore()
        receipts = FakeReceipts(make_receipt((1, "10"), day=receipt_day))
        handle_update(photo_update(1), make_ctx(store=store, receipts=receipts))
        assert store.rows[0].day == date(2026, 11, 18)


def test_unreadable_receipt_asks_for_manual_entry() -> None:
    tg, store = FakeTelegram(), FakeStore()
    kind = handle_update(photo_update(1), make_ctx(tg, store, receipts=FakeReceipts(None)))
    assert kind == "receipt_unreadable"
    assert store.rows == []
    assert "Wpisz wydatek ręcznie" in tg.sent[0]["text"]


def test_duplicate_photo_does_not_call_claude_again() -> None:
    store = FakeStore()
    receipts = FakeReceipts(make_receipt((1, "10")))
    ctx = make_ctx(store=store, receipts=receipts)
    handle_update(photo_update(1), ctx)
    assert handle_update(photo_update(1), ctx) == "duplicate"
    assert len(receipts.calls) == 1


def test_without_reader_bot_asks_for_manual_entry() -> None:
    tg = FakeTelegram()
    assert handle_update(photo_update(1), make_ctx(tg)) == "no_reader"
    assert "nie jest jeszcze włączony" in tg.sent[0]["text"]
    assert tg.downloaded == []


def test_image_sent_as_file_is_read() -> None:
    update = text_update(1, "")
    del update["message"]["text"]
    update["message"]["document"] = {"file_id": "doc1", "mime_type": "image/png"}
    receipts = FakeReceipts(make_receipt((1, "10")))
    assert handle_update(update, make_ctx(receipts=receipts)) == "receipt"
    assert receipts.calls[0][1] == "image/png"


def test_pdf_document_is_ignored() -> None:
    update = text_update(1, "")
    del update["message"]["text"]
    update["message"]["document"] = {"file_id": "doc1", "mime_type": "application/pdf"}
    receipts = FakeReceipts(make_receipt((1, "10")))
    assert handle_update(update, make_ctx(receipts=receipts)) == "ignored"


def test_receipt_date_uses_polish_time_of_message() -> None:
    late = int(datetime(2026, 11, 18, 0, 30, tzinfo=TZ).timestamp())
    store = FakeStore()
    receipts = FakeReceipts(make_receipt((1, "10"), day=None))
    handle_update(photo_update(1, date=late), make_ctx(store=store, receipts=receipts))
    assert store.rows[0].day == date(2026, 11, 18)
