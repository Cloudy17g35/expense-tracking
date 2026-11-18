from datetime import date

import pytest

from bot.summary import parse_month

TODAY = date(2026, 11, 18)


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("", (2026, 11)),
        ("10", (2026, 10)),
        ("12", (2025, 12)),
        ("2026-10", (2026, 10)),
        ("10.2025", (2025, 10)),
        ("10/2025", (2025, 10)),
        ("paź", (2026, 10)),
        ("październik", (2026, 10)),
        ("PAZDZIERNIK", (2026, 10)),
        ("styczeń", (2026, 1)),
        ("grudzień", (2025, 12)),
        ("grudzień 2026", (2026, 12)),
        ("lis", (2026, 11)),
    ],
)
def test_parse_month(arg: str, expected: tuple[int, int]) -> None:
    assert parse_month(arg, TODAY) == expected


@pytest.mark.parametrize("arg", ["13", "0", "xyz", "2026-13"])
def test_bad_month(arg: str) -> None:
    assert parse_month(arg, TODAY) is None
