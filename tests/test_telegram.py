import asyncio
import json

import httpx
import pytest

from app.spotify import playback
from app.telegram import Telegram, TelegramError


def setup_publisher(settings, store, mock_client, handler):
    settings.telegram_token = "synthetic-token"
    settings.telegram_chat = "@synthetic-channel"
    return Telegram(settings, store, mock_client(handler))


def test_one_message_survives_restart_and_escapes_html(settings, store, mock_client, player):
    calls = []

    def handler(request):
        calls.append((request.url.path.split("/")[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    telegram = setup_publisher(settings, store, mock_client, handler)
    payload = playback(player)
    asyncio.run(telegram.publish(payload))
    payload["progress_ms"] += 1000
    asyncio.run(telegram.publish(payload))
    restarted = Telegram(settings, store, telegram.client)
    payload["item"]["name"] = "Next"
    asyncio.run(restarted.publish(payload))
    asyncio.run(restarted.publish(playback(None)))
    asyncio.run(restarted.publish(playback(None)))
    assert [name for name, _ in calls] == ["sendMessage", "editMessageText", "editMessageText"]
    assert "&lt;track&gt;" in calls[0][1]["text"]
    assert "&amp;" in calls[0][1]["text"]
    assert calls[0][1]["text"].startswith('<a href="https://open.spotify.com/track/')
    assert "🎧" not in calls[0][1]["text"]
    assert calls[1][1]["message_id"] == 42
    assert calls[2][1]["text"] == "Сейчас ничего не слушаю"


@pytest.mark.parametrize(
    "error,expected",
    [
        ("Bad Request: message is not modified", ["editMessageText"]),
        ("Bad Request: message to edit not found", ["editMessageText", "sendMessage"]),
    ],
)
def test_edit_recovery(settings, store, mock_client, player, error, expected):
    calls = []

    def handler(request):
        method = request.url.path.split("/")[-1]
        calls.append(method)
        if method == "editMessageText":
            return httpx.Response(400, json={"ok": False, "error_code": 400, "description": error})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 43}})

    telegram = setup_publisher(settings, store, mock_client, handler)
    store.set(telegram.key, {"message_id": 42, "digest": "old"})
    asyncio.run(telegram.publish(playback(player)))
    assert calls == expected
    assert store.get(telegram.key)["message_id"] == (43 if len(expected) == 2 else 42)


def test_rate_limit_and_failure_dont_advance_state(settings, store, mock_client, player):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 120}})

    telegram = setup_publisher(settings, store, mock_client, handler)
    with pytest.raises(TelegramError):
        asyncio.run(telegram.publish(playback(player)))
    asyncio.run(telegram.publish(playback(player)))
    assert len(calls) == 1 and store.get(telegram.key) is None


def test_disabled_or_failed_playback_never_calls_telegram(settings, store, mock_client, player):
    def handler(_):
        pytest.fail("Unexpected Telegram request")

    telegram = Telegram(settings, store, mock_client(handler))
    asyncio.run(telegram.publish(playback(player)))
    telegram.settings.telegram_token = "test"
    asyncio.run(telegram.publish({"success": False}))
