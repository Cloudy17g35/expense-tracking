"""Obsługa pojedynczej aktualizacji z Telegrama."""

import logging
from html import escape

from bot.categories import CATEGORIES
from bot.config import Settings
from bot.telegram import TelegramAPI, Update

log = logging.getLogger(__name__)

HELP_TEXT = """<b>Jak dodać wydatek</b>

<b>Z palca:</b> <code>kwota [waluta] kategoria [opis]</code>
<code>45,50 spo biedronka</code>
<code>1500 sam rata leasingu</code>
<code>20 eur roz kawa w Wiedniu</code>
<code>350 czk sam parking Praga</code>

Waluta: domyślnie zł, można też <code>eur</code> i <code>czk</code>.
Bez kategorii zapytam przyciskami.

<b>Zdjęcie paragonu:</b> po prostu wyślij zdjęcie. W podpisie możesz wymusić kategorię lub walutę.

<b>Komendy:</b> /suma, /cofnij, /kategorie, /pomoc

Bot sprawdza wiadomości co kilka minut, więc odpowiedź może chwilę potrwać."""


def categories_text() -> str:
    lines = ["<b>Kategorie</b> (numer albo skrót):"]
    for c in CATEGORIES:
        aliases = ", ".join(f"<code>{a}</code>" for a in c.aliases)
        lines.append(f"{c.number}. {escape(c.name)}: {aliases}")
    return "\n".join(lines)


def parse_command(text: str) -> str | None:
    """'/pomoc@MojBot arg' -> 'pomoc'. Zwraca None, jeśli to nie komenda."""
    if not text.startswith("/"):
        return None
    head = text.split(maxsplit=1)[0][1:]
    return head.split("@", 1)[0].lower() or None


def handle_update(update: Update, settings: Settings, tg: TelegramAPI) -> str:
    """Przetwarza aktualizację i zwraca jej rodzaj (do liczników w logach)."""
    message = update.get("message")
    if not message:
        return "ignored"

    chat_id = message.get("chat", {}).get("id")
    if chat_id != settings.allowed_chat_id:
        return "foreign_chat"

    user_id = message.get("from", {}).get("id")
    if user_id not in settings.users:
        return "unknown_user"

    text: str = message.get("text") or ""
    command = parse_command(text)
    if command in ("pomoc", "help", "start"):
        tg.send_message(chat_id, HELP_TEXT, reply_to=message["message_id"])
        return "command"
    if command == "kategorie":
        tg.send_message(chat_id, categories_text(), reply_to=message["message_id"])
        return "command"

    return "ignored"
