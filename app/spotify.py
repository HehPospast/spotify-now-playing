import asyncio
import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from .lyrics import retry_after

TOKEN_URL = "https://accounts.spotify.com/api/token"
PLAYER_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SCOPE = "user-read-currently-playing"


class UpstreamError(Exception):
    def __init__(self, status, wait=0):
        self.status, self.wait = status, wait


def pkce_challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def playback(raw):
    raw = raw or {}
    item = raw.get("item")
    # Podcasts/ads/local files have no supported track/lyrics contract.
    if not isinstance(item, dict) or item.get("type") != "track" or not item.get("id"):
        item = None
    normalized = None
    if item:
        album = item.get("album") or {}
        normalized = {
            "id": item["id"],
            "type": "track",
            "name": item.get("name", ""),
            "artists": [{"name": artist.get("name", "")} for artist in item.get("artists", [])],
            "album": {
                "name": album.get("name", ""),
                "image_url": next(
                    (image["url"] for image in album.get("images", []) if image.get("url")), None
                ),
            },
            "duration_ms": item.get("duration_ms", 0),
            "explicit": bool(item.get("explicit")),
            "spotify_url": f"https://open.spotify.com/track/{item['id']}",
        }
    return {
        "success": True,
        "is_playing": bool(raw.get("is_playing")) and bool(normalized),
        "item": normalized,
        "progress_ms": raw.get("progress_ms") if normalized else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class Spotify:
    def __init__(self, settings, store, client):
        self.settings, self.store, self.client = settings, store, client
        self.lock = asyncio.Lock()
        self.retry_at = 0

    def authorize(self):
        state, browser, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        # Bounded: a new attempt invalidates the preceding one.
        self.store.set(
            "oauth", {"state": state, "browser": browser, "verifier": verifier, "expires": time.time() + 600}
        )
        params = {
            "client_id": self.settings.client_id,
            "response_type": "code",
            "redirect_uri": self.settings.redirect_uri,
            "scope": SCOPE,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": pkce_challenge(verifier),
        }
        return "https://accounts.spotify.com/authorize?" + urlencode(params), browser

    def consume_oauth(self, state, browser):
        pending = self.store.get("oauth")
        if (
            not pending
            or pending["expires"] < time.time()
            or not secrets.compare_digest(pending["state"].encode(), state.encode())
            or not secrets.compare_digest(pending["browser"].encode(), browser.encode())
        ):
            raise ValueError("Invalid or expired Spotify login. Start again from the setup page.")
        self.store.delete("oauth")
        return pending["verifier"]

    async def token_request(self, fields):
        try:
            response = await self.client.post(
                TOKEN_URL, data={"client_id": self.settings.client_id, **fields}
            )
        except httpx.RequestError:
            raise UpstreamError(502) from None
        if response.status_code == 429:
            wait = retry_after(response.headers.get("Retry-After"))
            self.retry_at = time.monotonic() + wait
            raise UpstreamError(429, wait)
        if response.status_code != 200:
            raise UpstreamError(response.status_code)
        return response.json()

    def save_tokens(self, data, old=None):
        refresh = data.get("refresh_token") or (old or {}).get("refresh_token")
        if not data.get("access_token") or not refresh:
            raise UpstreamError(502)
        tokens = {
            "access_token": data["access_token"],
            "refresh_token": refresh,
            "expires": time.time() + int(data.get("expires_in", 3600)),
        }
        self.store.set("tokens", tokens)
        return tokens

    async def connect(self, code, verifier):
        async with self.lock:
            data = await self.token_request(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.redirect_uri,
                    "code_verifier": verifier,
                }
            )
            self.save_tokens(data)
            self.retry_at = 0

    async def disconnect(self):
        async with self.lock:
            self.store.delete("tokens")
            self.store.delete("oauth")

    async def current(self):
        async with self.lock:
            tokens = self.store.get("tokens")
            if not tokens:
                return playback(None)
            if time.monotonic() < self.retry_at:
                raise UpstreamError(429, self.retry_at - time.monotonic())
            for attempt in range(2):
                if tokens["expires"] <= time.time() + 30:
                    try:
                        data = await self.token_request(
                            {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
                        )
                    except UpstreamError as exc:
                        if exc.status in (400, 401):
                            self.store.delete("tokens")
                        raise
                    tokens = self.save_tokens(data, tokens)
                try:
                    response = await self.client.get(
                        PLAYER_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
                    )
                except httpx.RequestError:
                    raise UpstreamError(502) from None
                if response.status_code == 401 and attempt == 0:
                    tokens["expires"] = 0
                    continue
                if response.status_code == 204:
                    return playback(None)
                if response.status_code == 429:
                    wait = retry_after(response.headers.get("Retry-After"))
                    self.retry_at = time.monotonic() + wait
                    raise UpstreamError(429, wait)
                if response.status_code != 200:
                    raise UpstreamError(response.status_code)
                return playback(response.json())
            raise UpstreamError(401)
