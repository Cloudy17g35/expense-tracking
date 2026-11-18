from bot.handlers import handle_update, parse_command
from tests.fakes import CHAT_ID, FakeTelegram, make_settings, text_update


def test_parse_command() -> None:
    assert parse_command("/pomoc") == "pomoc"
    assert parse_command("/Pomoc@MojBot jakis argument") == "pomoc"
    assert parse_command("45 spo") is None
    assert parse_command("/") is None


def test_help_command_replies_in_group() -> None:
    tg = FakeTelegram([])
    kind = handle_update(text_update(1, "/pomoc"), make_settings(), tg)
    assert kind == "command"
    assert len(tg.sent) == 1
    assert tg.sent[0]["chat_id"] == CHAT_ID
    assert tg.sent[0]["reply_to"] == 10
    assert "Jak dodać wydatek" in tg.sent[0]["text"]


def test_categories_command_lists_all() -> None:
    tg = FakeTelegram([])
    handle_update(text_update(1, "/kategorie"), make_settings(), tg)
    assert "7. Inne" in tg.sent[0]["text"]


def test_foreign_chat_is_ignored() -> None:
    tg = FakeTelegram([])
    kind = handle_update(text_update(1, "/pomoc", chat_id=-999), make_settings(), tg)
    assert kind == "foreign_chat"
    assert tg.sent == []


def test_unknown_user_is_ignored() -> None:
    tg = FakeTelegram([])
    kind = handle_update(text_update(1, "/pomoc", user_id=222), make_settings(), tg)
    assert kind == "unknown_user"
    assert tg.sent == []


def test_update_without_message_is_ignored() -> None:
    tg = FakeTelegram([])
    assert handle_update({"update_id": 1}, make_settings(), tg) == "ignored"
