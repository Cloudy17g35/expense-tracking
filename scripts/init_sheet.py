"""Przygotowuje arkusz: zakładki `Wydatki`, `Limity` i `Podsumowanie`.

Można uruchamiać wielokrotnie. Nie rusza istniejących danych ani wpisanych limitów:
`Limity` i `Podsumowanie` są zakładane tylko wtedy, gdy ich nie ma.
Uruchamiane z GitHub Actions: Actions → Init sheet → Run workflow.
"""

import json
import os
import sys
from typing import Any

import gspread
from gspread.utils import ValueInputOption

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.categories import CATEGORIES
from bot.sheets import HEADERS, LIMITS_WORKSHEET, SUMMARY_WORKSHEET, WORKSHEET

NUMBER = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}
RATE = {"numberFormat": {"type": "NUMBER", "pattern": "0.0000"}}
DATE = {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}
MONTH = {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm"}}
DATETIME = {"numberFormat": {"type": "DATE_TIME", "pattern": "yyyy-mm-dd hh:mm"}}
BOLD = {"textFormat": {"bold": True}}
SUMMARY_MONTHS = 24


def column(index: int) -> str:
    """1 -> 'A'."""
    return gspread.utils.rowcol_to_a1(1, index).rstrip("1")


def setup_expenses(spreadsheet: gspread.Spreadsheet) -> None:
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
    ws.format("A1:K1", BOLD)
    ws.batch_format(
        [
            {"range": "B2:B", "format": DATE},
            {"range": "F2:F", "format": NUMBER},
            {"range": "H2:H", "format": RATE},
            {"range": "I2:I", "format": NUMBER},
            {"range": "K2:K", "format": DATETIME},
        ]
    )


def setup_limits(spreadsheet: gspread.Spreadsheet) -> None:
    if LIMITS_WORKSHEET in [ws.title for ws in spreadsheet.worksheets()]:
        print(f"Zakładka {LIMITS_WORKSHEET} już istnieje, limity zostają bez zmian.")
        return
    ws = spreadsheet.add_worksheet(LIMITS_WORKSHEET, rows=len(CATEGORIES) + 5, cols=2)
    rows: list[list[Any]] = [["Kategoria", "Limit miesięczny (zł)"]]
    rows += [[c.name, ""] for c in CATEGORIES]
    ws.update(rows, "A1")
    ws.freeze(rows=1)
    ws.format("A1:B1", BOLD)
    ws.format(f"B2:B{len(rows)}", NUMBER)
    print(f"Dodano zakładkę {LIMITS_WORKSHEET}: wpisz limity w kolumnie B (puste = bez limitu).")


def setup_summary(spreadsheet: gspread.Spreadsheet) -> None:
    if SUMMARY_WORKSHEET in [ws.title for ws in spreadsheet.worksheets()]:
        print(f"Zakładka {SUMMARY_WORKSHEET} już istnieje.")
        return

    names = [c.name for c in CATEGORIES]
    last_category_col = column(1 + len(names))
    total_col = column(2 + len(names))
    first_month_row = 3
    last_month_row = first_month_row + SUMMARY_MONTHS - 1

    # Formuły w notacji angielskiej: API Arkuszy przyjmuje je tak niezależnie od języka arkusza.
    header: list[Any] = ["Miesiąc", *names, "Razem"]
    limits: list[Any] = ["Limit"]
    for index in range(len(names)):
        col = column(2 + index)
        limits.append(f'=IFERROR(VLOOKUP({col}$1,{LIMITS_WORKSHEET}!$A:$B,2,FALSE),"")')
    limits.append("")

    data = f"{WORKSHEET}!$I:$I"
    dates = f"{WORKSHEET}!$B:$B"
    cats = f"{WORKSHEET}!$D:$D"
    rows: list[list[Any]] = [header, limits]
    for row in range(first_month_row, last_month_row + 1):
        month = (
            "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)"
            if row == first_month_row
            else f"=EDATE(A{row - 1},-1)"
        )
        in_month = f'{dates},">="&$A{row},{dates},"<"&EDATE($A{row},1)'
        cells: list[Any] = [month]
        for index in range(len(names)):
            col = column(2 + index)
            cells.append(f"=SUMIFS({data},{cats},{col}$1,{in_month})")
        cells.append(f"=SUMIFS({data},{in_month})")
        rows.append(cells)

    ws = spreadsheet.add_worksheet(SUMMARY_WORKSHEET, rows=last_month_row + 2, cols=len(header))
    ws.update(rows, "A1", value_input_option=ValueInputOption.user_entered)
    ws.freeze(rows=2, cols=1)
    ws.format(f"A1:{total_col}2", BOLD)
    ws.format(f"A{first_month_row}:A{last_month_row}", MONTH)
    ws.format(f"B2:{total_col}{last_month_row}", NUMBER)

    # Czerwone tło, gdy wydatki w miesiącu przekraczają limit kategorii.
    spreadsheet.batch_update(
        {
            "requests": [
                {
                    "addConditionalFormatRule": {
                        "index": 0,
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": ws.id,
                                    "startRowIndex": first_month_row - 1,
                                    "endRowIndex": last_month_row,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": 1 + len(names),
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [
                                        {"userEnteredValue": "=AND(ISNUMBER(B$2),B$2>0,B3>B$2)"}
                                    ],
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.98, "green": 0.8, "blue": 0.8}
                                },
                            },
                        },
                    }
                }
            ]
        }
    )
    print(
        f"Dodano zakładkę {SUMMARY_WORKSHEET}: {SUMMARY_MONTHS} ostatnich miesięcy "
        f"i kategorie (B..{last_category_col}) + Razem."
    )


def main() -> None:
    client = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SA_JSON"]))
    spreadsheet = client.open_by_key(os.environ["SHEET_ID"])
    setup_expenses(spreadsheet)
    setup_limits(spreadsheet)
    setup_summary(spreadsheet)
    print("Gotowe.")


if __name__ == "__main__":
    main()
