"""Waluty i formatowanie kwot po polsku."""

from decimal import ROUND_HALF_UP, Decimal

BASE_CURRENCY = "PLN"

# Słowo w wiadomości (po normalizacji) -> kod waluty
CURRENCY_WORDS: dict[str, str] = {
    "zl": "PLN",
    "zł": "PLN",
    "pln": "PLN",
    "eur": "EUR",
    "euro": "EUR",
    "€": "EUR",
    "czk": "CZK",
    "kc": "CZK",
    "kč": "CZK",
}

SYMBOLS = {"PLN": "zł", "EUR": "€", "CZK": "Kč"}

CENT = Decimal("0.01")


def round2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def format_amount(amount: Decimal, currency: str = BASE_CURRENCY) -> str:
    """Decimal('1500.5'), 'PLN' -> '1 500,50 zł'."""
    text = f"{round2(amount):,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {SYMBOLS.get(currency, currency)}"
