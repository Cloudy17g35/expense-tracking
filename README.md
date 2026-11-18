# expense-tracking

Bot Telegram do śledzenia wydatków domowych. Domownicy wrzucają do wspólnej grupy zdjęcie paragonu albo krótką wiadomość, np. `45,50 spo biedronka`. Bot zapisuje wydatek we wspólnym arkuszu Google Sheets.

## Jak to działa

Nie ma serwera. Co kilka minut GitHub Actions ([`bot.yml`](.github/workflows/bot.yml)) uruchamia `python -m bot`. Skrypt:

1. pobiera z Telegrama oczekujące wiadomości (`getUpdates`),
2. przetwarza je (obecnie komendy `/pomoc` i `/kategorie`),
3. potwierdza w Telegramie tylko te, które udało się przetworzyć. Nieudane wracają przy następnym uruchomieniu.

Telegram przechowuje nieodebrane wiadomości przez 24 h. Workflow [`keepalive.yml`](.github/workflows/keepalive.yml) co miesiąc ponownie włącza harmonogram, bo GitHub wyłącza crony po 60 dniach bez commitów.

## Konfiguracja

Sekrety repozytorium (*Settings → Secrets and variables → Actions*):

| Sekret | Opis |
|---|---|
| `TELEGRAM_TOKEN` | token bota od @BotFather |
| `ALLOWED_CHAT_ID` | ID grupy, np. `-100…` |
| `USERS` | JSON `{"<telegram_user_id>": "<imię>"}` |

Dopóki sekrety nie są ustawione, workflow bota kończy się bez błędu i nic nie robi. Kolejne iteracje dodadzą `SHEET_ID`, `GOOGLE_SA_JSON` i `ANTHROPIC_API_KEY`.

Repo jest publiczne: kod nie zawiera żadnych ID ani imion, a logi pokazują tylko liczniki przetworzonych wiadomości.

## Praca lokalna

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Ręczne uruchomienie bota: utwórz plik `.env` (jest w `.gitignore`) ze zmiennymi `TELEGRAM_TOKEN`, `ALLOWED_CHAT_ID` i `USERS`, potem `uv run python -m bot`.
