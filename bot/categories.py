"""Kategorie wydatków i dopasowanie skrótów wpisywanych w wiadomościach."""

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    number: int
    name: str
    aliases: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category(1, "Spożywcze i domowe", ("spo", "spoz", "jedzenie")),
    Category(2, "Odzież i obuwie", ("odz", "ubrania")),
    Category(3, "Samochód", ("sam", "auto", "paliwo")),
    Category(4, "Mieszkanie i rachunki", ("dom", "rach", "media")),
    Category(5, "Zdrowie i uroda", ("zdr", "apteka")),
    Category(6, "Rozrywka i jedzenie na mieście", ("roz", "rest", "kawa")),
    Category(7, "Inne", ("inne",)),
)

MIN_PREFIX = 3


def normalize(text: str) -> str:
    """Małe litery bez polskich znaków: 'Spożywcze' -> 'spozywcze'."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def by_number(number: int) -> Category | None:
    return next((c for c in CATEGORIES if c.number == number), None)


def match_category(token: str) -> Category | None:
    """Dopasuj słowo do kategorii: numer 1-7, alias albo prefiks nazwy/aliasu (min. 3 znaki)."""
    word = normalize(token.strip())
    if not word:
        return None
    if word.isdigit():
        return by_number(int(word))
    for category in CATEGORIES:
        if word in category.aliases:
            return category
    if len(word) < MIN_PREFIX:
        return None
    for category in CATEGORIES:
        first_word = normalize(category.name).split()[0]
        candidates = (first_word, *category.aliases)
        # 'spoż' -> 'spozywcze'; tylko w tę stronę, żeby np. 'sport' nie pasował do aliasu 'spo'.
        if any(c.startswith(word) for c in candidates):
            return category
    return None
