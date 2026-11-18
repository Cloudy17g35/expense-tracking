"""Odczyt zdjęcia paragonu przez Claude: sklep, data, suma, waluta, podział na kategorie."""

import base64
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol, cast

import anthropic
from anthropic.types.beta import BetaUserMessageParam
from pydantic import BaseModel, Field

from bot.categories import CATEGORIES, Category, by_number
from bot.money import BASE_CURRENCY, round2

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Modele z serwerowym fallbackiem przy odmowie (Haiku go nie ma).
FALLBACK_MODEL_PREFIXES = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")


def supports_fallback(model: str) -> bool:
    return model.startswith(FALLBACK_MODEL_PREFIXES)


OTHER = 7

ImageType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
IMAGE_TYPES: tuple[str, ...] = ("image/jpeg", "image/png", "image/gif", "image/webp")


class _Split(BaseModel):
    category: int = Field(description="Numer kategorii 1-7")
    amount: float = Field(description="Kwota tej kategorii po rabatach")


class _ReceiptOutput(BaseModel):
    readable: bool = Field(description="false, jeśli to nie paragon lub nie da się odczytać sumy")
    merchant: str = Field(description="Nazwa sklepu, krótko, np. 'Biedronka'")
    date: str = Field(description="Data zakupu YYYY-MM-DD albo pusty tekst")
    total: float = Field(description="Suma do zapłaty")
    currency: str = Field(description="Kod waluty ISO, np. PLN, EUR, CZK")
    splits: list[_Split]


@dataclass(frozen=True)
class ReceiptSplit:
    category: Category
    amount: Decimal


@dataclass(frozen=True)
class Receipt:
    merchant: str
    day: date | None
    total: Decimal
    currency: str
    splits: tuple[ReceiptSplit, ...]


class ReceiptReader(Protocol):
    def read(self, image: bytes, media_type: str) -> Receipt | None: ...


def _category_list() -> str:
    hints = {
        1: "jedzenie do domu, napoje, chemia, środki czystości, artykuły gospodarcze",
        2: "ubrania, buty, dodatki",
        3: "paliwo, myjnia, parking, części, serwis, akcesoria samochodowe",
        4: "rachunki, wyposażenie mieszkania, narzędzia, dekoracje",
        5: "apteka, leki, kosmetyki, higiena osobista, suplementy",
        6: "restauracja, kawiarnia, fast food, kino, rozrywka, prezenty",
        7: "wszystko, co nie pasuje do innych kategorii",
    }
    return "\n".join(f"{c.number}. {c.name}: {hints[c.number]}" for c in CATEGORIES)


SYSTEM_PROMPT = f"""Odczytujesz zdjęcia paragonów dla domowego budżetu \
(Polska, czasem Czechy i strefa euro).

Zwróć:
- merchant: krótka nazwa sklepu,
- date: data zakupu z paragonu (YYYY-MM-DD) albo pusty tekst, jeśli jej nie widać,
- total: kwota faktycznie zapłacona (po rabatach, z kaucją),
- currency: waluta paragonu (PLN, EUR, CZK...),
- splits: podział sumy na kategorie. Przypisz każdą pozycję do jednej kategorii, \
rabat odejmij od kategorii pozycji, której dotyczy, kaucję dolicz do kategorii produktu. \
Suma kwot w splits musi być równa total. Jedna kategoria to jeden element listy.

Kategorie:
{_category_list()}

Jeśli zdjęcie nie jest paragonem albo suma jest nieczytelna, ustaw readable na false."""


def normalize(output: _ReceiptOutput) -> Receipt | None:
    """Sprawdza i porządkuje odpowiedź modelu. None, gdy paragon jest nieczytelny."""
    total = round2(Decimal(str(output.total)))
    if not output.readable or total <= 0:
        return None

    amounts: dict[int, Decimal] = {}
    for split in output.splits:
        number = split.category if by_number(split.category) else OTHER
        amounts[number] = amounts.get(number, Decimal(0)) + round2(Decimal(str(split.amount)))
    amounts = {n: a for n, a in amounts.items() if a > 0}
    if not amounts:
        amounts = {OTHER: total}

    # Różnicę z zaokrągleń lub błędu modelu dopisz do największej kategorii.
    difference = total - sum(amounts.values(), Decimal(0))
    if difference:
        largest = max(amounts, key=lambda n: amounts[n])
        amounts[largest] += difference
        if amounts[largest] <= 0:
            amounts = {largest: total}

    try:
        day: date | None = date.fromisoformat(output.date) if output.date else None
    except ValueError:
        day = None

    currency = (output.currency or BASE_CURRENCY).strip().upper()
    splits = tuple(
        ReceiptSplit(category=c, amount=amounts[n])
        for n in sorted(amounts, key=lambda n: -amounts[n])
        if (c := by_number(n)) is not None
    )
    return Receipt(
        merchant=output.merchant.strip(),
        day=day,
        total=total,
        currency=currency,
        splits=splits,
    )


class ClaudeReceiptReader:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self._model = model
        self._fallback = supports_fallback(model)

    def read(self, image: bytes, media_type: str) -> Receipt | None:
        message: BetaUserMessageParam = {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": cast(ImageType, media_type),
                        "data": base64.standard_b64encode(image).decode(),
                    },
                },
                {"type": "text", "text": "Odczytaj ten paragon."},
            ],
        }
        try:
            response = self._client.beta.messages.parse(
                model=self._model,
                max_tokens=16000,
                betas=[FALLBACK_BETA] if self._fallback else anthropic.omit,
                fallbacks="default" if self._fallback else anthropic.omit,
                output_config={"effort": "low"},
                system=SYSTEM_PROMPT,
                messages=[message],
                output_format=_ReceiptOutput,
            )
        except anthropic.BadRequestError as error:
            # Np. zbyt duży lub uszkodzony obraz: ponawianie nic nie da.
            log.warning("Claude odrzucił zdjęcie: %s", error.message)
            return None
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            # Zły klucz: nie blokujemy kolejki, użytkownik dostanie prośbę o wpis ręczny.
            log.error("Claude API: nieprawidłowy klucz ANTHROPIC_API_KEY lub brak uprawnień")
            return None

        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            log.warning("Brak odczytu paragonu (stop_reason=%s)", response.stop_reason)
            return None
        return normalize(response.parsed_output)
