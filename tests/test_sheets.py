from datetime import date, datetime
from decimal import Decimal

from bot.sheets import HEADERS, ExpenseRow, to_serial


def test_to_serial_matches_spreadsheet_epoch() -> None:
    assert to_serial(date(1899, 12, 31)) == 1
    assert to_serial(date(2026, 11, 18)) == 46344
    assert to_serial(datetime(2026, 11, 18, 12, 0)) == 46344.5


def test_row_values_follow_headers() -> None:
    row = ExpenseRow(
        expense_id="-100-45",
        day=date(2026, 11, 18),
        who="Ania",
        category="Rozrywka i jedzenie na mieście",
        description="kawa",
        amount=Decimal("20"),
        currency="EUR",
        rate=Decimal("4.2345"),
        amount_pln=Decimal("84.69"),
        source="ręcznie",
        added=datetime(2026, 11, 18, 12, 0),
    )
    values = row.to_values()
    assert len(values) == len(HEADERS)
    assert values[0] == "-100-45"
    assert values[5] == 20.0
    assert values[8] == 84.69


def test_row_round_trips_through_sheet_values() -> None:
    original = ExpenseRow(
        expense_id="-100-45",
        day=date(2026, 11, 18),
        who="Ania",
        category="Inne",
        description="x",
        amount=Decimal("20.5"),
        currency="EUR",
        rate=Decimal("4.2345"),
        amount_pln=Decimal("86.81"),
        source="ręcznie",
        added=datetime(2026, 11, 18, 12, 0),
    )
    parsed = ExpenseRow.from_values(original.to_values())
    assert parsed is not None
    assert parsed.day == original.day
    assert parsed.amount == Decimal("20.5")
    assert parsed.amount_pln == Decimal("86.81")
    assert parsed.added == original.added


def test_from_values_tolerates_hand_edited_cells() -> None:
    parsed = ExpenseRow.from_values(
        ["id", 46344, "Ania", "Inne", "", "1 234,50", "PLN", "", "1234,5"]
    )
    assert parsed is not None
    assert parsed.amount == Decimal("1234.50")
    assert parsed.rate == 1


def test_from_values_skips_broken_rows() -> None:
    assert ExpenseRow.from_values([]) is None
    assert ExpenseRow.from_values(["", 46344]) is None
    assert ExpenseRow.from_values(["id", "nie data", "A", "B", "", "1", "PLN", "1", "1"]) is None


def test_appended_rows_from_range() -> None:
    from bot.sheets import appended_rows, column_formats

    assert appended_rows("Wydatki!A5:K6") == (5, 6)
    assert appended_rows("Wydatki!A12:K12") == (12, 12)
    assert appended_rows("Wydatki!A7") == (7, 7)
    assert appended_rows("") is None
    formats = column_formats(5, 6)
    assert formats[0] == {
        "range": "B5:B6",
        "format": {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}},
    }
    assert column_formats(2)[0]["range"] == "B2:B"
