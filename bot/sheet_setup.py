"""Zakładanie zakładek arkusza: `Wydatki`, `Limity` i `Podsumowanie`.

Można uruchamiać wielokrotnie:
- `Wydatki`: dane zostają, poprawiane są tylko nagłówki i formaty,
- `Limity`: zakładane tylko, gdy ich nie ma (wpisane limity zostają),
- `Podsumowanie`: zawsze generowane od nowa (same formuły, bez danych).

Wywoływane przez workflow *Init sheet* (scripts/init_sheet.py) oraz automatycznie przez
bota, gdy w arkuszu brakuje zakładki `Wydatki`.
"""

import logging
from typing import Any

import gspread
from gspread.utils import ValueInputOption, ValueRenderOption, rowcol_to_a1

from bot.categories import CATEGORIES
from bot.sheets import (
    HEADERS,
    LIMITS_WORKSHEET,
    MONTH,
    NUMBER,
    SUMMARY_WORKSHEET,
    WORKSHEET,
    column_formats,
)

log = logging.getLogger(__name__)

BOLD = {"textFormat": {"bold": True}}
SUMMARY_MONTHS = 24
FIRST_MONTH_ROW = 3


def column(index: int) -> str:
    """1 -> 'A'."""
    return rowcol_to_a1(1, index).rstrip("1")


def _titles(spreadsheet: gspread.Spreadsheet) -> list[str]:
    return [ws.title for ws in spreadsheet.worksheets()]


def setup_expenses(spreadsheet: gspread.Spreadsheet) -> None:
    titles = _titles(spreadsheet)
    if WORKSHEET in titles:
        ws = spreadsheet.worksheet(WORKSHEET)
        log.info("Zakładka %s już istnieje.", WORKSHEET)
    elif len(titles) == 1 and not any(spreadsheet.sheet1.get_all_values()):
        ws = spreadsheet.sheet1
        ws.update_title(WORKSHEET)
        log.info("Zmieniono nazwę pustej zakładki na %s.", WORKSHEET)
    else:
        ws = spreadsheet.add_worksheet(WORKSHEET, rows=1000, cols=len(HEADERS))
        log.info("Dodano zakładkę %s.", WORKSHEET)

    ws.update([HEADERS], "A1")
    ws.freeze(rows=1)
    ws.format(f"A1:{column(len(HEADERS))}1", BOLD)
    ws.batch_format(column_formats(2))


def setup_limits(spreadsheet: gspread.Spreadsheet) -> None:
    if LIMITS_WORKSHEET in _titles(spreadsheet):
        log.info("Zakładka %s już istnieje, limity zostają bez zmian.", LIMITS_WORKSHEET)
        return
    ws = spreadsheet.add_worksheet(LIMITS_WORKSHEET, rows=len(CATEGORIES) + 5, cols=2)
    rows: list[list[Any]] = [["Kategoria", "Limit miesięczny (zł)"]]
    rows += [[c.name, ""] for c in CATEGORIES]
    ws.update(rows, "A1")
    ws.freeze(rows=1)
    ws.format("A1:B1", BOLD)
    ws.format(f"B2:B{len(rows)}", NUMBER)
    log.info("Dodano zakładkę %s: limity wpisuje się w kolumnie B.", LIMITS_WORKSHEET)


def summary_rows(sep: str = ",") -> list[list[Any]]:
    """Nagłówek, wiersz limitów i 24 miesiące z formułami.

    `sep` to separator argumentów: formuły są parsowane jak wpisane ręcznie, więc w arkuszu
    z polskimi ustawieniami regionalnymi (przecinek dziesiętny) separatorem jest średnik.
    """
    names = [c.name for c in CATEGORIES]
    header: list[Any] = ["Miesiąc", *names, "Razem"]
    # 1/(1/x) zamienia pusty limit (0) na błąd, a ten IFERROR na pusty tekst. Dzięki temu
    # reguła „wydatki > limit” nie zaznacza kategorii bez limitu (liczba > tekst = FAŁSZ).
    limits: list[Any] = ["Limit"]
    for index in range(len(names)):
        col = column(2 + index)
        limits.append(f'=IFERROR(1/(1/VLOOKUP({col}$1,{LIMITS_WORKSHEET}!$A:$B,2,FALSE)),"")')
    limits.append("")

    amounts = f"{WORKSHEET}!$I:$I"
    dates = f"{WORKSHEET}!$B:$B"
    categories = f"{WORKSHEET}!$D:$D"
    rows: list[list[Any]] = [header, limits]
    for row in range(FIRST_MONTH_ROW, FIRST_MONTH_ROW + SUMMARY_MONTHS):
        if row == FIRST_MONTH_ROW:
            month = "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)"
        else:
            month = f"=EDATE(A{row - 1},-1)"
        in_month = f'{dates},">="&$A{row},{dates},"<"&EDATE($A{row},1)'
        cells: list[Any] = [month]
        for index in range(len(names)):
            col = column(2 + index)
            cells.append(f"=SUMIFS({amounts},{categories},{col}$1,{in_month})")
        cells.append(f"=SUMIFS({amounts},{in_month})")
        rows.append(cells)
    if sep != ",":
        # W formułach nie ma przecinków dziesiętnych ani w tekstach, więc zamiana jest bezpieczna.
        rows = [[_with_separator(v, sep) for v in row] for row in rows]
    return rows


def _with_separator(value: Any, sep: str) -> Any:
    if isinstance(value, str) and value.startswith("="):
        return value.replace(",", sep)
    return value


def setup_summary(spreadsheet: gspread.Spreadsheet) -> None:
    if SUMMARY_WORKSHEET in _titles(spreadsheet):
        spreadsheet.del_worksheet(spreadsheet.worksheet(SUMMARY_WORKSHEET))
    rows = summary_rows()
    width = len(rows[0])
    total_col = column(width)
    last_row = len(rows)

    ws = spreadsheet.add_worksheet(SUMMARY_WORKSHEET, rows=last_row + 2, cols=width)
    ws.update(rows, "A1", value_input_option=ValueInputOption.user_entered)
    if _formula_errors(ws, last_row, total_col):
        log.info("Formuły z przecinkami nie działają w tym arkuszu, używam średników.")
        ws.update(summary_rows(";"), "A1", value_input_option=ValueInputOption.user_entered)
    ws.freeze(rows=2, cols=1)
    ws.format(f"A1:{total_col}2", BOLD)
    ws.format(f"A{FIRST_MONTH_ROW}:A{last_row}", MONTH)
    ws.format(f"B2:{total_col}{last_row}", NUMBER)

    # Czerwone tło, gdy wydatki w miesiącu przekraczają limit kategorii. Formuła bez
    # separatorów argumentów: reguły formatowania są parsowane zgodnie z językiem arkusza
    # (w polskim separatorem jest średnik), więc „=AND(a,b)” zostałoby odrzucone.
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
                                    "startRowIndex": FIRST_MONTH_ROW - 1,
                                    "endRowIndex": last_row,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": width - 1,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": f"=B{FIRST_MONTH_ROW}>B$2"}],
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
    if errors := _formula_errors(ws, last_row, total_col):
        raise RuntimeError(f"Formuły w {SUMMARY_WORKSHEET} zwracają błędy: {errors[:5]}")
    log.info("Formuły w %s liczą się poprawnie.", SUMMARY_WORKSHEET)
    log.info("Zakładka %s wygenerowana (%d miesięcy).", SUMMARY_WORKSHEET, SUMMARY_MONTHS)


def _formula_errors(ws: gspread.Worksheet, last_row: int, total_col: str) -> list[str]:
    """Adresy komórek z błędem formuły. Bez kwot w logach (repo publiczne)."""
    values = ws.get_values(
        f"A2:{total_col}{last_row}", value_render_option=ValueRenderOption.formatted
    )
    return [
        f"{column(c + 1)}{r + 2}={v}"
        for r, row in enumerate(values)
        for c, v in enumerate(row)
        if isinstance(v, str) and v.startswith("#")
    ]


def setup_all(spreadsheet: gspread.Spreadsheet) -> None:
    setup_expenses(spreadsheet)
    setup_limits(spreadsheet)
    setup_summary(spreadsheet)
