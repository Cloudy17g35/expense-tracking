from decimal import Decimal

import pytest

from bot.money import format_amount
from bot.parse import parse_expense


@pytest.mark.parametrize(
    ("text", "amount", "currency", "category", "description"),
    [
        ("45,50 spo biedronka", "45.50", "PLN", 1, "biedronka"),
        ("1500 sam rata leasingu", "1500", "PLN", 3, "rata leasingu"),
        ("20 eur roz kawa w Wiedniu", "20", "EUR", 6, "kawa w Wiedniu"),
        ("350 czk sam parking Praga", "350", "CZK", 3, "parking Praga"),
        ("biedronka 45.5 spo", "45.5", "PLN", 1, "biedronka"),
        ("spożywcze 12", "12", "PLN", 1, ""),
        ("45,50zł spo", "45.50", "PLN", 1, ""),
        ("20€ roz", "20", "EUR", 6, ""),
        ("€20 roz", "20", "EUR", 6, ""),
        ("100 Kč roz", "100", "CZK", 6, ""),
        ("12 3", "12", "PLN", 3, ""),
        ("30 ZŁ odzież buty Zalando", "30", "PLN", 2, "buty Zalando"),
        ("120 apteka", "120", "PLN", 5, ""),
    ],
)
def test_parses_expense(
    text: str, amount: str, currency: str, category: int, description: str
) -> None:
    parsed = parse_expense(text)
    assert parsed is not None
    assert parsed.amount == Decimal(amount)
    assert parsed.currency == currency
    assert parsed.category is not None
    assert parsed.category.number == category
    assert parsed.description == description


def test_missing_category_is_allowed_when_starting_with_amount() -> None:
    parsed = parse_expense("45 biedronka")
    assert parsed is not None
    assert parsed.category is None
    assert parsed.description == "biedronka"


def test_first_category_wins_rest_goes_to_description() -> None:
    parsed = parse_expense("20 roz kawa")
    assert parsed is not None
    assert parsed.category is not None and parsed.category.number == 6
    assert parsed.description == "kawa"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "cześć, co na obiad?",
        "kupiłem 2 bułki",
        "o 15:30 u mamy",
        "0 spo",
        "/pomoc",
        "spo biedronka",
    ],
)
def test_conversation_is_not_an_expense(text: str) -> None:
    assert parse_expense(text) is None


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("45.5", "PLN", "45,50 zł"),
        ("1500", "PLN", "1 500,00 zł"),
        ("20", "EUR", "20,00 €"),
        ("350", "CZK", "350,00 Kč"),
        ("0.005", "PLN", "0,01 zł"),
    ],
)
def test_format_amount(amount: str, currency: str, expected: str) -> None:
    assert format_amount(Decimal(amount), currency) == expected
