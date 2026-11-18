from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from bot.fx import FxError, NbpRates

EUR_URL = "https://api.nbp.pl/api/exchangerates/rates/a/eur/2026-11-05/2026-11-15/"


def nbp_response(*rates: tuple[str, float]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "table": "A",
            "code": "EUR",
            "rates": [{"no": "x", "effectiveDate": d, "mid": m} for d, m in rates],
        },
    )


def test_pln_needs_no_request() -> None:
    assert NbpRates().rate("PLN", date(2026, 11, 15)) == Decimal(1)


@respx.mock
def test_weekend_uses_last_business_day() -> None:
    # 2026-11-15 to niedziela; ostatnie notowanie w piątek 13.11.
    route = respx.get(EUR_URL).mock(
        return_value=nbp_response(("2026-11-12", 4.2101), ("2026-11-13", 4.2345))
    )
    rates = NbpRates()
    assert rates.rate("EUR", date(2026, 11, 15)) == Decimal("4.2345")
    assert rates.rate("EUR", date(2026, 11, 15)) == Decimal("4.2345")
    assert route.call_count == 1  # drugi raz z cache


@respx.mock
def test_missing_data_raises() -> None:
    respx.get(EUR_URL).mock(return_value=httpx.Response(404, text="Not Found"))
    with pytest.raises(FxError):
        NbpRates().rate("EUR", date(2026, 11, 15))
