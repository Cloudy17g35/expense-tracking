from bot.categories import CATEGORIES
from bot.sheet_setup import SUMMARY_MONTHS, column, summary_rows


def test_column_letters() -> None:
    assert [column(i) for i in (1, 2, 8, 9, 26, 27)] == ["A", "B", "H", "I", "Z", "AA"]


def test_summary_layout() -> None:
    rows = summary_rows()
    assert rows[0] == ["Miesiąc", *[c.name for c in CATEGORIES], "Razem"]
    assert len(rows) == 2 + SUMMARY_MONTHS
    assert all(len(r) == len(rows[0]) for r in rows)
    assert rows[1][1] == '=IFERROR(1/(1/VLOOKUP(B$1,Limity!$A:$B,2,FALSE)),"")'
    assert rows[2][0] == "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)"
    assert rows[3][0] == "=EDATE(A3,-1)"
    assert rows[2][1] == (
        "=SUMIFS(Wydatki!$I:$I,Wydatki!$D:$D,B$1,"
        'Wydatki!$B:$B,">="&$A3,Wydatki!$B:$B,"<"&EDATE($A3,1))'
    )
    assert rows[-1][-1].startswith("=SUMIFS(Wydatki!$I:$I,Wydatki!$B:$B")
