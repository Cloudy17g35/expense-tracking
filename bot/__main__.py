"""Jedno uruchomienie bota: pobierz oczekujące wiadomości, przetwórz, potwierdź.

Uruchamiane cyklicznie przez GitHub Actions (.github/workflows/bot.yml).
"""

import logging
import sys
from collections import Counter

from bot.config import Settings
from bot.handlers import handle_update
from bot.telegram import TelegramAPI, TelegramClient

log = logging.getLogger("bot")


def run(settings: Settings, tg: TelegramAPI) -> Counter[str]:
    """Przetwarza wszystkie oczekujące aktualizacje.

    Aktualizacja jest potwierdzana w Telegramie (przez offset) dopiero po udanym
    przetworzeniu. Przy błędzie przerywamy, a nieudana aktualizacja i kolejne
    wrócą przy następnym uruchomieniu.
    """
    stats: Counter[str] = Counter()
    offset: int | None = None
    while True:
        updates = tg.get_updates(offset)
        if not updates:
            return stats
        for update in updates:
            try:
                stats[handle_update(update, settings, tg)] += 1
            except Exception:
                log.exception(
                    "Błąd przy aktualizacji %s, ponowię w następnym uruchomieniu",
                    update.get("update_id"),
                )
                stats["error"] += 1
                if offset is not None:
                    tg.get_updates(offset)  # potwierdź to, co już się udało
                return stats
            offset = update["update_id"] + 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()  # wartości ze zmiennych środowiskowych
    tg = TelegramClient(settings.telegram_token.get_secret_value())
    stats = run(settings, tg)
    # Repo jest publiczne: logujemy tylko liczniki, bez treści wiadomości.
    log.info("Przetworzono: %s", dict(stats) or "brak nowych wiadomości")
    return 1 if stats["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
