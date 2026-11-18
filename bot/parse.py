"""Parser wiadomości „z palca”: `<kwota> [waluta] <kategoria> [opis]`, w dowolnej kolejności."""

import re
from dataclasses import dataclass
from decimal import Decimal

from bot.categories import Category, match_category
from bot.money import BASE_CURRENCY, CURRENCY_WORDS

_CURRENCY_PATTERN = "|".join(re.escape(w) for w in sorted(CURRENCY_WORDS, key=len, reverse=True))
# '45', '45,50', '45.5', '45,50zł', '20€', '€20'
_AMOUNT_RE = re.compile(
    rf"^(?P<pre>{_CURRENCY_PATTERN})?(?P<num>\d+(?:[.,]\d{{1,2}})?)(?P<post>{_CURRENCY_PATTERN})?$",
    re.IGNORECASE,
)
_PUNCTUATION = ".,;:!?"


@dataclass(frozen=True)
class ParsedExpense:
    amount: Decimal
    currency: str
    category: Category | None
    description: str


def _parse_amount(token: str) -> tuple[Decimal, str | None] | None:
    # Bez obcinania kropki i przecinka: należą do kwoty („45,50”).
    match = _AMOUNT_RE.match(token.rstrip("!?;:"))
    if not match:
        return None
    amount = Decimal(match["num"].replace(",", "."))
    word = (match["pre"] or match["post"] or "").lower()
    return amount, CURRENCY_WORDS.get(word)


@dataclass(frozen=True)
class Scan:
    """Wszystko, co udało się rozpoznać w tekście, bez oceny, czy to wydatek."""

    amount: Decimal | None
    currency: str | None
    category: Category | None
    description: str
    starts_with_amount: bool


def scan(text: str) -> Scan:
    amount: Decimal | None = None
    currency: str | None = None
    category: Category | None = None
    rest: list[str] = []
    starts_with_amount = False

    for index, token in enumerate(text.split()):
        if amount is None and (parsed := _parse_amount(token)):
            amount, token_currency = parsed
            currency = currency or token_currency
            starts_with_amount = index == 0
            continue
        word = token.lower().strip(_PUNCTUATION)
        if currency is None and word in CURRENCY_WORDS:
            currency = CURRENCY_WORDS[word]
            continue
        # Cyfra 1-7 to kategoria dopiero po kwocie, żeby „3 sam” było kwotą 3 zł.
        if category is None and (amount is not None or not word.isdigit()):
            found = match_category(word)
            if found is not None:
                category = found
                continue
        rest.append(token)

    return Scan(amount, currency, category, " ".join(rest), starts_with_amount)


def parse_expense(text: str) -> ParsedExpense | None:
    """Zwraca wydatek albo None, jeśli wiadomość to zwykła rozmowa.

    Wiadomość uznajemy za wydatek, gdy zaczyna się od kwoty albo gdy zawiera
    kwotę i kategorię. Dzięki temu „kupiłem 2 bułki” nie tworzy wpisu.
    """
    if not text.strip() or text.startswith("/"):
        return None
    found = scan(text)
    if found.amount is None or found.amount <= 0:
        return None
    if not found.starts_with_amount and found.category is None:
        return None
    return ParsedExpense(
        amount=found.amount,
        currency=found.currency or BASE_CURRENCY,
        category=found.category,
        description=found.description,
    )
