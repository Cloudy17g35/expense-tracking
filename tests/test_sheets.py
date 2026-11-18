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
