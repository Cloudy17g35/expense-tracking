import httpx
import pytest
import respx

from bot.telegram import TelegramClient, TelegramError

BASE = "https://api.telegram.org/botTOKEN"


def client(sleeps: list[float]) -> TelegramClient:
    return TelegramClient("TOKEN", sleep=sleeps.append)


@respx.mock
def test_timeout_is_retried() -> None:
    route = respx.post(f"{BASE}/getFile").mock(
        side_effect=[
            httpx.ReadTimeout("timed out"),
            httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/a.jpg"}}),
        ]
    )
    respx.get("https://api.telegram.org/file/botTOKEN/photos/a.jpg").mock(
        return_value=httpx.Response(200, content=b"img")
    )
    sleeps: list[float] = []
    assert client(sleeps).download_file("f1") == b"img"
    assert route.call_count == 2
    assert sleeps == [2]


@respx.mock
def test_server_error_then_success() -> None:
    respx.post(f"{BASE}/getUpdates").mock(
        side_effect=[
            httpx.Response(502, text="Bad Gateway"),
            httpx.Response(200, json={"ok": True, "result": []}),
        ]
    )
    assert client([]).get_updates(None) == []


@respx.mock
def test_rate_limit_uses_retry_after() -> None:
    respx.post(f"{BASE}/sendMessage").mock(
        side_effect=[
            httpx.Response(
                429,
                json={
                    "ok": False,
                    "description": "Too Many Requests",
                    "parameters": {"retry_after": 7},
                },
            ),
            httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}),
        ]
    )
    sleeps: list[float] = []
    client(sleeps).send_message(1, "x")
    assert sleeps == [7]


@respx.mock
def test_gives_up_after_all_attempts() -> None:
    respx.post(f"{BASE}/getFile").mock(side_effect=httpx.ConnectTimeout("nope"))
    sleeps: list[float] = []
    with pytest.raises(httpx.ConnectTimeout):
        client(sleeps).download_file("f1")
    assert sleeps == [2, 5, 10]


@respx.mock
def test_api_error_is_not_retried() -> None:
    route = respx.post(f"{BASE}/editMessageText").mock(
        return_value=httpx.Response(
            400, json={"ok": False, "description": "Bad Request: message is not modified"}
        )
    )
    with pytest.raises(TelegramError, match="not modified"):
        client([]).edit_message_text(1, 2, "x")
    assert route.call_count == 1
