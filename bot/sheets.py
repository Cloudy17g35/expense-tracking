"""Zapis wydatków w Google Sheets (konto usługi, zakładka `Wydatki`)."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

import gspread

WORKSHEET = "Wydatki"
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


class ExpenseStore(Protocol):
    def has_id(self, expense_id: str) -> bool: ...

    def append(self, rows: list[ExpenseRow]) -> None: ...

    def set_category(self, expense_id: str, category: str) -> int: ...


class GoogleSheetStore:
    def __init__(self, worksheet: gspread.Worksheet) -> None:
        self._ws = worksheet

    @classmethod
    def connect(cls, service_account_json: str, sheet_id: str) -> "GoogleSheetStore":
        client = gspread.service_account_from_dict(json.loads(service_account_json))
        return cls(client.open_by_key(sheet_id).worksheet(WORKSHEET))

    def _row_numbers(self, expense_id: str) -> list[int]:
        ids = self._ws.col_values(COL_ID)
        return [i for i, value in enumerate(ids, start=1) if i > 1 and value == expense_id]

    def has_id(self, expense_id: str) -> bool:
        return bool(self._row_numbers(expense_id))

    def append(self, rows: list[ExpenseRow]) -> None:
        self._ws.append_rows(
            [r.to_values() for r in rows],
            value_input_option=gspread.utils.ValueInputOption.raw,
            insert_data_option=gspread.utils.InsertDataOption.insert_rows,
            table_range="A1",
        )

    def set_category(self, expense_id: str, category: str) -> int:
        rows = self._row_numbers(expense_id)
        for row in rows:
            self._ws.update_cell(row, COL_CATEGORY, category)
        return len(rows)
