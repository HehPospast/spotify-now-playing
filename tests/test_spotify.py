import asyncio
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.spotify import Spotify, UpstreamError, pkce_challenge, playback


def test_pkce_and_single_use_browser_bound_state(settings, store, mock_client):
    spotify = Spotify(settings, store, mock_client(lambda _: httpx.Response(204)))
    url, browser = spotify.authorize()
    query = parse_qs(urlsplit(url).query)
    pending = store.get("oauth")
    assert query["code_challenge"] == [pkce_challenge(pending["verifier"])]
    assert query["scope"] == ["user-read-currently-playing"]
    assert "client_secret" not in query
    with pytest.raises(ValueError):
        spotify.consume_oauth(pending["state"], "wrong browser")
    assert spotify.consume_oauth(pending["state"], browser) == pending["verifier"]
    with pytest.raises(ValueError):
        spotify.consume_oauth(pending["state"], browser)


def test_expired_and_replaced_states(settings, store, mock_client):
    spotify = Spotify(settings, store, mock_client(lambda _: httpx.Response(204)))
    _, first_browser = spotify.authorize()
    first = store.get("oauth")
    spotify.authorize()
    with pytest.raises(ValueError):
        spotify.consume_oauth(first["state"], first_browser)
    expired = store.get("oauth")
    expired["expires"] = 0
    store.set("oauth", expired)
    with pytest.raises(ValueError):
        spotify.consume_oauth(expired["state"], expired["browser"])


def test_tokens_are_encrypted(settings, store, mock_client):
    spotify = Spotify(settings, store, mock_client(lambda _: httpx.Response(204)))
    spotify.save_tokens({"access_token": "secret-access", "refresh_token": "secret-refresh"})
    row = store.db.execute("SELECT value FROM state WHERE key='tokens'").fetchone()[0]
    assert b"secret-access" not in row and b"secret-refresh" not in row
    assert store.get("tokens")["refresh_token"] == "secret-refresh"


@pytest.mark.parametrize("rotate", [True, False])
def test_refresh_preserves_or_rotates_refresh_token(settings, store, mock_client, player, rotate):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/token"):
            data = {"access_token": "new-access", "expires_in": 3600}
            if rotate:
                data["refresh_token"] = "new-refresh"
            return httpx.Response(200, json=data)
        assert request.headers["Authorization"] == "Bearer new-access"
        return httpx.Response(200, json=player)

    spotify = Spotify(settings, store, mock_client(handler))
    store.set("tokens", {"access_token": "old", "refresh_token": "old-refresh", "expires": 0})
    result = asyncio.run(spotify.current())
    assert result["item"]["name"] == "Test <track>"
    assert len(calls) == 2
    assert store.get("tokens")["refresh_token"] == ("new-refresh" if rotate else "old-refresh")


def test_401_refresh_and_retry(settings, store, mock_client, player):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        return httpx.Response(401) if len(calls) == 1 else httpx.Response(200, json=player)

    spotify = Spotify(settings, store, mock_client(handler))
    spotify.save_tokens({"access_token": "old", "refresh_token": "refresh"})
    assert asyncio.run(spotify.current())["is_playing"]
    assert len(calls) == 3


def test_429_respects_cooldown(settings, store, mock_client):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})

    spotify = Spotify(settings, store, mock_client(handler))
    spotify.save_tokens({"access_token": "a", "refresh_token": "r"})
    for _ in range(2):
        with pytest.raises(UpstreamError) as exc:
            asyncio.run(spotify.current())
        assert exc.value.wait > 119
    assert len(calls) == 1


def test_invalid_refresh_requires_reconnect(settings, store, mock_client):
    spotify = Spotify(settings, store, mock_client(lambda _: httpx.Response(400)))
    store.set("tokens", {"access_token": "a", "refresh_token": "r", "expires": time.time() - 1})
    with pytest.raises(UpstreamError):
        asyncio.run(spotify.current())
    assert store.get("tokens") is None


def test_idle_and_unsupported_media(player):
    assert playback(None)["item"] is None
    player["item"]["type"] = "episode"
    assert playback(player)["item"] is None


def test_exchange_uses_verifier_and_disconnect_removes_tokens(settings, store, mock_client):
    def handler(request):
        body = parse_qs(request.content.decode())
        assert body["code_verifier"] == ["test-verifier"]
        assert body["client_id"] == ["test-client"]
        assert "client_secret" not in body
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r"})

    spotify = Spotify(settings, store, mock_client(handler))
    asyncio.run(spotify.connect("test-code", "test-verifier"))
    assert store.get("tokens")
    asyncio.run(spotify.disconnect())
    assert store.get("tokens") is None
