from typing import Any

import pytest

import bot.__main__ as main_module
from bot.__main__ import run
from tests.fakes import FakeTelegram, make_ctx, text_update


def test_no_updates() -> None:
    tg = FakeTelegram([])
    assert run(make_ctx(tg)) == {}
    assert tg.offsets == [None]


def test_processes_and_acknowledges_all() -> None:
    tg = FakeTelegram([text_update(5, "/pomoc"), text_update(6, "zwykła rozmowa")])
    stats = run(make_ctx(tg))
    assert stats == {"command": 1, "ignored": 1}
    assert tg.pending == []
    assert tg.offsets == [None, 7]


def test_error_stops_and_keeps_failed_update(monkeypatch: pytest.MonkeyPatch) -> None:
    def flaky(update: dict[str, Any], *_: Any) -> str:
        if update["update_id"] == 6:
            raise RuntimeError("boom")
        return "ok"

    monkeypatch.setattr(main_module, "handle_update", flaky)
    tg = FakeTelegram([text_update(5, "a"), text_update(6, "b"), text_update(7, "c")])
    stats = run(make_ctx(tg))
    assert stats == {"ok": 1, "error": 1}
    # 5 potwierdzone, 6 i 7 czekają na kolejne uruchomienie
    assert [u["update_id"] for u in tg.pending] == [6, 7]


def test_error_on_first_update_acknowledges_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "handle_update", broken)
    tg = FakeTelegram([text_update(5, "a")])
    run(make_ctx(tg))
    assert tg.offsets == [None]
    assert len(tg.pending) == 1
