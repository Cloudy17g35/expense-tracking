from datetime import date
from decimal import Decimal

from bot.receipt import SYSTEM_PROMPT, _ReceiptOutput, _Split, normalize


def output(**overrides: object) -> _ReceiptOutput:
    data: dict[str, object] = {
        "readable": True,
        "merchant": " Biedronka ",
        "date": "2026-11-17",
        "total": 123.45,
        "currency": "pln",
        "splits": [_Split(category=1, amount=100.0), _Split(category=2, amount=23.45)],
    }
    data.update(overrides)
    return _ReceiptOutput.model_validate(data)


def test_normalize_happy_path() -> None:
    receipt = normalize(output())
    assert receipt is not None
    assert receipt.merchant == "Biedronka"
    assert receipt.day == date(2026, 11, 17)
    assert receipt.total == Decimal("123.45")
    assert receipt.currency == "PLN"
    assert [(s.category.number, s.amount) for s in receipt.splits] == [
        (1, Decimal("100.00")),
        (2, Decimal("23.45")),
    ]


def test_unreadable_returns_none() -> None:
    assert normalize(output(readable=False)) is None
    assert normalize(output(total=0)) is None


def test_splits_are_fixed_to_match_total() -> None:
    receipt = normalize(
        output(splits=[_Split(category=1, amount=100.0), _Split(category=2, amount=23.0)])
    )
    assert receipt is not None
    assert sum(s.amount for s in receipt.splits) == receipt.total
    assert receipt.splits[0].amount == Decimal("100.45")


def test_same_category_is_merged_and_unknown_goes_to_other() -> None:
    receipt = normalize(
        output(
            splits=[
                _Split(category=1, amount=50.0),
                _Split(category=1, amount=50.0),
                _Split(category=42, amount=23.45),
            ]
        )
    )
    assert receipt is not None
    assert [(s.category.number, s.amount) for s in receipt.splits] == [
        (1, Decimal("100.00")),
        (7, Decimal("23.45")),
    ]


def test_no_splits_means_other() -> None:
    receipt = normalize(output(splits=[]))
    assert receipt is not None
    assert [(s.category.number, s.amount) for s in receipt.splits] == [(7, Decimal("123.45"))]


def test_bad_date_is_dropped() -> None:
    receipt = normalize(output(date="17.11.2026"))
    assert receipt is not None and receipt.day is None
    receipt = normalize(output(date=""))
    assert receipt is not None and receipt.day is None


def test_prompt_lists_all_categories() -> None:
    for number in range(1, 8):
        assert f"\n{number}. " in SYSTEM_PROMPT
