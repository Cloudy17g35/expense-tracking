# expense-tracking

Bot Telegram do śledzenia wydatków domowych. Domownicy wrzucają do wspólnej grupy zdjęcie paragonu albo krótką wiadomość, np. `45,50 spo biedronka`. Bot zapisuje wydatek we wspólnym arkuszu Google Sheets.

## Jak dodać wydatek

`<kwota> [waluta] <kategoria> [opis]`, w dowolnej kolejności:

```
45,50 spo biedronka
1500 sam rata leasingu
20 eur roz kawa w Wiedniu
350 czk sam parking Praga
```

- **Kto:** ustalane z nadawcy wiadomości.
- **Waluta:** domyślnie zł; `eur`/`€` i `czk`/`kč` przeliczane na zł kursem średnim NBP z dnia wydatku (w weekend z ostatniego notowania).
- **Data:** moment wysłania wiadomości, a nie przetworzenia przez bota.
- **Bez kategorii** (np. `45 biedronka`): bot zapisuje wpis jako „❓ do wyboru” i pyta przyciskami.
- **Zwykła rozmowa** jest ignorowana. Wpis powstaje, gdy wiadomość zaczyna się od kwoty albo zawiera kwotę i kategorię.

| # | Kategoria | Skróty |
|---|---|---|
| 1 | Spożywcze i domowe | `spo`, `spoz`, `jedzenie` |
| 2 | Odzież i obuwie | `odz`, `ubrania` |
| 3 | Samochód | `sam`, `auto`, `paliwo` |
| 4 | Mieszkanie i rachunki | `dom`, `rach`, `media` |
| 5 | Zdrowie i uroda | `zdr`, `apteka` |
| 6 | Rozrywka i jedzenie na mieście | `roz`, `rest`, `kawa` |
| 7 | Inne | `inne` |

Działa też numer kategorii (1–7), pełna nazwa oraz pisownia bez polskich znaków.

## Zdjęcie paragonu

Wyślij zdjęcie paragonu (albo obraz jako plik). Claude odczytuje sklep, datę, sumę, walutę i dzieli sumę na kategorie, np. zakupy spożywcze i koszulka z jednego marketu. W arkuszu powstaje wtedy jeden wiersz na każdą kategorię, wszystkie z tym samym ID.

- **Data:** z paragonu, jeśli jest czytelna i nie starsza niż 60 dni; w przeciwnym razie data wysłania zdjęcia.
- **Podpis pod zdjęciem nadpisuje odczyt:** `dom` (cała kwota do jednej kategorii), `80 eur` (inna kwota lub waluta). Pozostałe słowa trafiają do opisu.
- **Nieczytelne zdjęcie:** bot prosi o wpis ręczny.

## Jak to działa

Nie ma serwera. Co kilka minut GitHub Actions ([`bot.yml`](.github/workflows/bot.yml)) uruchamia `python -m bot`. Skrypt:

1. pobiera z Telegrama oczekujące wiadomości i kliknięcia przycisków (`getUpdates`),
2. zapisuje wydatki w zakładce `Wydatki` i odpowiada w grupie,
3. potwierdza w Telegramie tylko to, co udało się przetworzyć. Nieudane wracają przy następnym uruchomieniu, a ID wpisu (`<czat>-<wiadomość>`) chroni przed podwójnym zapisem.

Telegram przechowuje nieodebrane wiadomości przez 24 h. Workflow [`keepalive.yml`](.github/workflows/keepalive.yml) co miesiąc ponownie włącza harmonogram, bo GitHub wyłącza crony po 60 dniach bez commitów.

## Konfiguracja

Sekrety repozytorium (*Settings → Secrets and variables → Actions*):

| Sekret | Opis |
|---|---|
| `TELEGRAM_TOKEN` | token bota od @BotFather |
| `ALLOWED_CHAT_ID` | ID grupy, np. `-100…` |
| `USERS` | JSON `{"<telegram_user_id>": "<imię>"}` |
| `SHEET_ID` | ID arkusza z adresu `docs.google.com/spreadsheets/d/<ID>/edit` |
| `GOOGLE_SA_JSON` | cała zawartość pliku klucza konta usługi Google |
| `ANTHROPIC_API_KEY` | klucz Claude API do odczytu zdjęć paragonów |

Opcjonalna **zmienna** repozytorium `CLAUDE_MODEL` (*Settings → Secrets and variables → Actions → Variables*) wybiera model. Domyślnie `claude-opus-5-5` (najdokładniejszy, rzędu kilku groszy za paragon); `claude-haiku-5-5` jest wielokrotnie tańszy. Zapytanie ma włączony serwerowy fallback, gdy model odmówi odpowiedzi.

Arkusz trzeba udostępnić mailowi konta usługi jako Edytor, a potem raz uruchomić *Actions → Init sheet → Run workflow*. To założy zakładkę `Wydatki` z nagłówkami i formatami.

Bez pierwszych trzech sekretów workflow bota nic nie robi. Bez `SHEET_ID`/`GOOGLE_SA_JSON` bot odpowiada na komendy, ale wydatków nie zapisuje (i mówi o tym w grupie). Bez `ANTHROPIC_API_KEY` na zdjęcia odpowiada prośbą o wpis ręczny.

Repo jest publiczne: kod nie zawiera żadnych ID ani imion, a logi pokazują tylko liczniki przetworzonych wiadomości.

## Praca lokalna

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Ręczne uruchomienie bota: utwórz plik `.env` (jest w `.gitignore`) z powyższymi zmiennymi, potem `uv run python -m bot`.
