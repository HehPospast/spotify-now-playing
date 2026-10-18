import asyncio
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import Runtime, create_app
from app.spotify import playback


def test_owner_auth_callback_cookie_and_public_contract(settings):
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "private-a", "refresh_token": "private-r"})
        return httpx.Response(204)

    app = create_app(settings, httpx.MockTransport(handler))
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/admin/status").status_code == 401
        assert client.post("/auth/spotify", data={"admin_key": "bad"}).status_code == 401
        assert client.post("/auth/spotify", data={"admin_key": "неверный ключ"}).status_code == 401
        login = client.post("/auth/spotify", data={"admin_key": settings.admin_key}, follow_redirects=False)
        assert login.status_code == 303
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=lax" in login.headers["set-cookie"]
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        assert client.get("/auth/callback", params={"state": "bad", "code": "code"}).status_code == 400
        callback = client.get(
            "/auth/callback", params={"state": state, "code": "code"}, follow_redirects=False
        )
        assert callback.status_code == 303 and callback.headers["location"] == "/setup?spotify=connected"
        assert client.get("/auth/callback", params={"state": state, "code": "code"}).status_code == 400
        status = client.get("/api/admin/status", headers={"X-Admin-Key": settings.admin_key})
        assert status.json()["connected"] is True
        public = client.get("/api/v1/spotify/public/currently-playing")
        assert "private-" not in public.text
        assert public.headers["cache-control"] == "no-store"
        assert client.post("/api/admin/disconnect").status_code == 401
        result = client.post("/api/admin/disconnect", headers={"X-Admin-Key": settings.admin_key})
        assert result.json() == {"connected": False}
        assert client.get("/api/v1/spotify/public/currently-playing").json()["item"] is None


def test_oauth_wrong_browser_denial_and_rate_limit(settings):
    app = create_app(settings, httpx.MockTransport(lambda _: httpx.Response(204)))
    with TestClient(app) as client:
        login = client.post("/auth/spotify", data={"admin_key": settings.admin_key}, follow_redirects=False)
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        cookie = client.cookies.get("spotify_oauth")
        client.cookies.clear()
        assert client.get("/auth/callback", params={"state": state, "code": "a"}).status_code == 400
        client.cookies.set("spotify_oauth", cookie, path="/auth")
        denied = client.get(
            "/auth/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False
        )
        assert denied.headers["location"] == "/setup?spotify=denied"
        for _ in range(9):
            assert client.post("/auth/spotify", data={"admin_key": "bad"}).status_code == 401
        assert client.post("/auth/spotify", data={"admin_key": "bad"}).status_code == 429


def test_bounded_fanout_uses_shared_snapshot(settings, store, mock_client, player):
    runtime = Runtime(settings, store, mock_client(lambda _: httpx.Response(204)))
    queue = asyncio.Queue(maxsize=2)
    runtime.queues.add(queue)
    for progress in range(10):
        runtime.publish({**playback(player), "progress_ms": progress})
    assert queue.qsize() == 2
    assert queue.get_nowait()["progress_ms"] == 8
    assert queue.get_nowait()["progress_ms"] == 9


def test_startup_does_not_publish_idle_before_spotify_responds(settings, store, mock_client):
    runtime = Runtime(settings, store, mock_client(lambda _: pytest.fail("Unexpected upstream request")))
    settings.telegram_token = "synthetic-token"
    settings.telegram_chat = "@synthetic-channel"
    asyncio.run(runtime.telegram.publish(runtime.snapshot))
    assert runtime.snapshot["success"] is False


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:8080/auth/callback",
        "http://example.com/auth/callback",
        "https://example.com/wrong",
        "https://example.com/auth/callback?bad=1",
    ],
)
def test_invalid_redirect_uri(settings, uri):
    settings.redirect_uri = uri
    with pytest.raises(ValueError):
        settings.validate()
