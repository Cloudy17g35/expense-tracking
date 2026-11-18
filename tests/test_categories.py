import pytest

from bot.categories import match_category, normalize


def test_normalize_strips_polish_characters() -> None:
    assert normalize("Spożywcze ŁÓDŹ") == "spozywcze lodz"


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("spo", 1),
        ("SPO", 1),
        ("spoż", 1),
        ("spożywcze", 1),
        ("odz", 2),
        ("odzież", 2),
        ("sam", 3),
        ("samochód", 3),
        ("paliwo", 3),
        ("dom", 4),
        ("media", 4),
        ("zdr", 5),
        ("apteka", 5),
        ("roz", 6),
        ("kawa", 6),
        ("inne", 7),
        ("3", 3),
        ("7", 7),
    ],
)
def test_match_category(token: str, expected: int) -> None:
    category = match_category(token)
    assert category is not None
    assert category.number == expected


@pytest.mark.parametrize("token", ["", "x", "sp", "8", "0", "biedronka", "sport"])
def test_no_match(token: str) -> None:
    assert match_category(token) is None
