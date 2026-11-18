"""Przygotowuje arkusz: zakładka `Wydatki`, nagłówki, formaty kolumn.

Można uruchamiać wielokrotnie. Istniejących danych nie rusza.
Uruchamiane z GitHub Actions: Actions → Init sheet → Run workflow.
"""

import json
import os
import sys

import gspread

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.sheets import HEADERS, WORKSHEET

NUMBER = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}
RATE = {"numberFormat": {"type": "NUMBER", "pattern": "0.0000"}}
DATE = {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}
DATETIME = {"numberFormat": {"type": "DATE_TIME", "pattern": "yyyy-mm-dd hh:mm"}}


def main() -> None:
    client = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SA_JSON"]))
    spreadsheet = client.open_by_key(os.environ["SHEET_ID"])

    titles = [ws.title for ws in spreadsheet.worksheets()]
    if WORKSHEET in titles:
        ws = spreadsheet.worksheet(WORKSHEET)
        print(f"Zakładka {WORKSHEET} już istnieje.")
    elif len(titles) == 1 and not any(spreadsheet.sheet1.get_all_values()):
        ws = spreadsheet.sheet1
        ws.update_title(WORKSHEET)
        print(f"Zmieniono nazwę pustej zakładki na {WORKSHEET}.")
    else:
        ws = spreadsheet.add_worksheet(WORKSHEET, rows=1000, cols=len(HEADERS))
        print(f"Dodano zakładkę {WORKSHEET}.")

    ws.update([HEADERS], "A1")
    ws.freeze(rows=1)
    ws.format("A1:K1", {"textFormat": {"bold": True}})
    ws.batch_format(
        [
            {"range": "B2:B", "format": DATE},
            {"range": "F2:F", "format": NUMBER},
            {"range": "H2:H", "format": RATE},
            {"range": "I2:I", "format": NUMBER},
            {"range": "K2:K", "format": DATETIME},
        ]
    )
    print("Gotowe: nagłówki i formaty kolumn ustawione.")


if __name__ == "__main__":
    main()
