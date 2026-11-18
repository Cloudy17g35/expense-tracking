"""Kursy walut z API NBP (tabela A, kurs średni)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

import httpx

from bot.money import BASE_CURRENCY

NBP_URL = "https://api.nbp.pl/api/exchangerates/rates/a/{code}/{start}/{end}/"
# Najdłuższa przerwa między notowaniami (święta + weekend) to kilka dni.
LOOKBACK_DAYS = 10


class FxError(RuntimeError):
    pass


class RateProvider(Protocol):
    def rate(self, currency: str, day: date) -> Decimal: ...


class NbpRates:
    """Kurs z dnia wydatku, a w weekend lub święto z ostatniego wcześniejszego notowania."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=15, headers={"Accept": "application/json"})
        self._cache: dict[tuple[str, date], Decimal] = {}

    def rate(self, currency: str, day: date) -> Decimal:
        if currency == BASE_CURRENCY:
            return Decimal(1)
        key = (currency, day)
        if key not in self._cache:
            self._cache[key] = self._fetch(currency, day)
        return self._cache[key]

    def _fetch(self, currency: str, day: date) -> Decimal:
        url = NBP_URL.format(
            code=currency.lower(),
            start=(day - timedelta(days=LOOKBACK_DAYS)).isoformat(),
            end=day.isoformat(),
        )
        response = self._http.get(url)
        if response.status_code != 200:
            raise FxError(f"NBP {currency} {day}: HTTP {response.status_code}")
        rates = response.json().get("rates") or []
        valid = [r for r in rates if r["effectiveDate"] <= day.isoformat()]
        if not valid:
            raise FxError(f"NBP {currency} {day}: brak notowań")
        latest = max(valid, key=lambda r: r["effectiveDate"])
        return Decimal(str(latest["mid"]))
