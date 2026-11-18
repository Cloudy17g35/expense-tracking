"""Wydatki w Google Sheets (konto usługi): zakładki `Wydatki` i `Limity`."""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import gspread
from gspread.utils import InsertDataOption, ValueInputOption, ValueRenderOption

log = logging.getLogger(__name__)

WORKSHEET = "Wydatki"
LIMITS_WORKSHEET = "Limity"
SUMMARY_WORKSHEET = "Podsumowanie"
HEADERS = [
    "ID",
    "Data",
    "Kto",
    "Kategoria",
    "Opis/sklep",
    "Kwota",
    "Waluta",
    "Kurs NBP",
    "Kwota PLN",
    "Źródło",
    "Dodano",
]
COL_ID = 1
COL_CATEGORY = 4
UNKNOWN_CATEGORY = "❓ do wyboru"

# Arkusze liczą daty jako dni od 30.12.1899. Zapisujemy liczby (RAW), żeby nie zależeć
# od ustawień regionalnych arkusza (przecinek vs kropka, format daty).
_EPOCH = datetime(1899, 12, 30)


def to_serial(value: date | datetime) -> float:
    if not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    delta = value.replace(tzinfo=None) - _EPOCH
    return round(delta.days + delta.seconds / 86400, 6)


def from_serial(value: Any) -> datetime:
    return _EPOCH + timedelta(days=float(value))


def to_decimal(value: Any) -> Decimal | None:
    """Liczba z komórki; tekst wpisany ręcznie może mieć przecinek lub spacje."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class ExpenseRow:
    expense_id: str
    day: date
    who: str
    category: str
    description: str
    amount: Decimal
    currency: str
    rate: Decimal
    amount_pln: Decimal
    source: str
    added: datetime

    def to_values(self) -> list[Any]:
        return [
            self.expense_id,
            to_serial(self.day),
            self.who,
            self.category,
            self.description,
            float(self.amount),
            self.currency,
            float(self.rate),
            float(self.amount_pln),
            self.source,
            to_serial(self.added),
        ]

    @classmethod
    def from_values(cls, values: list[Any]) -> "ExpenseRow | None":
        """Wiersz odczytany z arkusza (wartości niesformatowane). None, gdy niepoprawny."""
        cells = [*values, *[""] * (len(HEADERS) - len(values))]
        amount, rate, amount_pln = (to_decimal(cells[i]) for i in (5, 7, 8))
        if not cells[0] or amount is None or amount_pln is None:
            return None
        try:
            day = from_serial(cells[1]).date()
            added = (
                from_serial(cells[10])
                if cells[10] != ""
                else datetime.combine(day, datetime.min.time())
            )
        except (TypeError, ValueError):
            return None
        return cls(
            expense_id=str(cells[0]),
            day=day,
            who=str(cells[2]),
            category=str(cells[3]),
            description=str(cells[4]),
            amount=amount,
            currency=str(cells[6]) or "PLN",
            rate=rate if rate is not None else Decimal(1),
            amount_pln=amount_pln,
            source=str(cells[9]),
            added=added,
        )


class ExpenseStore(Protocol):
    def has_id(self, expense_id: str) -> bool: ...

    def append(self, rows: list[ExpenseRow]) -> None: ...

    def set_category(self, expense_id: str, category: str) -> int: ...

    def all_rows(self) -> list[ExpenseRow]: ...

    def delete(self, expense_id: str) -> int: ...

    def limits(self) -> dict[str, Decimal]: ...


def rows_for(store: ExpenseStore, expense_id: str) -> list[ExpenseRow]:
    return [r for r in store.all_rows() if r.expense_id == expense_id]


class GoogleSheetStore:
    def __init__(self, spreadsheet: gspread.Spreadsheet) -> None:
        self._spreadsheet = spreadsheet
        self._ws = spreadsheet.worksheet(WORKSHEET)

    @classmethod
    def connect(cls, service_account_json: str, sheet_id: str) -> "GoogleSheetStore":
        client = gspread.service_account_from_dict(json.loads(service_account_json))
        spreadsheet = client.open_by_key(sheet_id)
        try:
            return cls(spreadsheet)
        except gspread.exceptions.WorksheetNotFound:
            # Świeży arkusz bez uruchomionego „Init sheet”: zakładamy zakładki sami.
            from bot.sheet_setup import setup_all

            log.warning("Brak zakładki %s, zakładam zakładki arkusza", WORKSHEET)
            setup_all(spreadsheet)
            return cls(spreadsheet)

    def _row_numbers(self, expense_id: str) -> list[int]:
        ids = self._ws.col_values(COL_ID)
        return [i for i, value in enumerate(ids, start=1) if i > 1 and value == expense_id]

    def has_id(self, expense_id: str) -> bool:
        return bool(self._row_numbers(expense_id))

    def append(self, rows: list[ExpenseRow]) -> None:
        self._ws.append_rows(
            [r.to_values() for r in rows],
            value_input_option=ValueInputOption.raw,
            insert_data_option=InsertDataOption.insert_rows,
            table_range="A1",
        )

    def set_category(self, expense_id: str, category: str) -> int:
        rows = self._row_numbers(expense_id)
        for row in rows:
            self._ws.update_cell(row, COL_CATEGORY, category)
        return len(rows)

    def all_rows(self) -> list[ExpenseRow]:
        values = self._ws.get_all_values(value_render_option=ValueRenderOption.unformatted)
        parsed = (ExpenseRow.from_values(list(v)) for v in values[1:])
        return [r for r in parsed if r is not None]

    def delete(self, expense_id: str) -> int:
        rows = self._row_numbers(expense_id)
        # Od końca, żeby usuwanie nie przesuwało numerów pozostałych wierszy.
        for row in reversed(rows):
            self._ws.delete_rows(row)
        return len(rows)

    def limits(self) -> dict[str, Decimal]:
        try:
            ws = self._spreadsheet.worksheet(LIMITS_WORKSHEET)
        except gspread.exceptions.WorksheetNotFound:
            return {}
        result: dict[str, Decimal] = {}
        values = ws.get_all_values(value_render_option=ValueRenderOption.unformatted)
        for row in values[1:]:
            if len(row) >= 2 and (limit := to_decimal(row[1])) is not None and limit > 0:
                result[str(row[0])] = limit
        return result
