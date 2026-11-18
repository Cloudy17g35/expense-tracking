"""Podsumowanie miesiąca dla komendy /suma."""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from html import escape

from bot.categories import CATEGORIES, normalize
from bot.money import format_amount
from bot.sheets import ExpenseRow

MONTHS = [
    "styczeń",
    "luty",
    "marzec",
    "kwiecień",
    "maj",
    "czerwiec",
    "lipiec",
    "sierpień",
    "wrzesień",
    "październik",
    "listopad",
    "grudzień",
]
# 'lis', 'listopad', 'listopadzie'... -> 11
_MONTH_PREFIXES = {normalize(name)[:3]: number for number, name in enumerate(MONTHS, start=1)}
_NUMERIC = re.compile(r"^(?:(\d{4})[-./])?(\d{1,2})(?:[-./](\d{4}))?$")


def parse_month(arg: str, today: date) -> tuple[int, int] | None:
    """'' -> bieżący miesiąc; '10', '2026-10', '10.2026', 'paź', 'październik'."""
    arg = arg.strip()
    if not arg:
        return today.year, today.month
    words = arg.split()
    year: int | None = None
    if len(words) == 2 and words[1].isdigit() and len(words[1]) == 4:
        year = int(words[1])
        arg = words[0]
    month: int | None = None
    if match := _NUMERIC.match(arg):
        year = int(match[1] or match[3]) if (match[1] or match[3]) else year
        month = int(match[2])
    else:
        month = _MONTH_PREFIXES.get(normalize(arg)[:3])
    if month is None or not 1 <= month <= 12:
        return None
    if year is None:
        # Bez roku: ostatni taki miesiąc, który już był (w styczniu „gru” = zeszły rok).
        year = today.year if month <= today.month else today.year - 1
    return year, month


def month_summary(rows: list[ExpenseRow], year: int, month: int, limits: dict[str, Decimal]) -> str:
    title = f"{MONTHS[month - 1].capitalize()} {year}"
    selected = [r for r in rows if r.day.year == year and r.day.month == month]
    if not selected:
        return f"📊 <b>{title}</b>: brak wydatków."

    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_person: dict[str, Decimal] = defaultdict(Decimal)
    for row in selected:
        by_category[row.category] += row.amount_pln
        by_person[row.who] += row.amount_pln
    total = sum(by_category.values(), Decimal(0))

    order = {c.name: c.number for c in CATEGORIES}
    lines = [f"📊 <b>{title}</b>: {format_amount(total)}", ""]
    for name in sorted(by_category, key=lambda n: (order.get(n, 99), n)):
        amount = by_category[name]
        line = f"• {escape(name)}: {format_amount(amount)}"
        if (limit := limits.get(name)) is not None:
            percent = int(amount * 100 / limit)
            warning = " ⚠️" if amount > limit else ""
            line += f" ({percent}% z {format_amount(limit)}){warning}"
        lines.append(line)
    for name, limit in limits.items():
        if name not in by_category:
            lines.append(f"• {escape(name)}: 0,00 zł (0% z {format_amount(limit)})")

    if len(by_person) > 1:
        people = ", ".join(
            f"{escape(who)} {format_amount(amount)}"
            for who, amount in sorted(by_person.items(), key=lambda kv: -kv[1])
        )
        lines += ["", f"Kto: {people}"]
    return "\n".join(lines)
