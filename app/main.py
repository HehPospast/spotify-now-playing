import asyncio
import contextlib
import json
import logging
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .lyrics import SpicyLyricsService, state
from .spotify import Spotify, UpstreamError, playback
from .storage import Store
from .telegram import Telegram, TelegramError

logger = logging.getLogger(__name__)
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class Runtime:
    def __init__(self, settings, store, client):
        self.settings, self.store = settings, store
        self.spotify = Spotify(settings, store, client)
        self.telegram = Telegram(settings, store, client)
        self.lyrics = SpicyLyricsService(secret_key=settings.lyrics_key)
        self.snapshot = {"success": False, "error": "connecting", "item": None}
        self.queues = set()
        self.wake = asyncio.Event()
        self.lyrics_task = None
        self.tasks = []
        self.login_attempts = deque(maxlen=20)

    def publish(self, payload):
        self.snapshot = payload
        for queue in self.queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(payload)

    async def finish_lyrics(self, track_id):
        lyrics = await self.lyrics.get(track_id)
        if (self.snapshot.get("item") or {}).get("id") == track_id:
            self.publish({**self.snapshot, "lyrics": lyrics})

    async def poll_once(self):
        payload = await self.spotify.current()
        track_id = (payload.get("item") or {}).get("id")
        if track_id and self.settings.lyrics_key:
            cached = self.lyrics.peek(track_id)
            payload["lyrics"] = cached or state(track_id, "loading")
            if cached is None and (self.lyrics_task is None or self.lyrics_task.done()):
                self.lyrics_task = asyncio.create_task(self.finish_lyrics(track_id))
        self.publish(payload)

    async def poll_loop(self):
        failures = 0
        while True:
            self.wake.clear()
            delay = self.settings.poll_seconds
            try:
                await self.poll_once()
                failures = 0
            except UpstreamError as exc:
                failures += 1
                delay = max(delay, exc.wait, min(300, 2 ** min(failures, 8)))
                self.publish({"success": False, "error": "spotify_unavailable", "item": None})
                logger.warning("Spotify unavailable (status %s); retrying later", exc.status)
            except Exception:
                delay = max(delay, 30)
                self.publish({"success": False, "error": "spotify_unavailable", "item": None})
                logger.warning("Playback update failed; retrying later")
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def telegram_loop(self):
        while True:
            try:
                await self.telegram.publish(self.snapshot)
            except TelegramError as exc:
                logger.warning("Telegram update failed (status %s); retrying later", exc.code)
            except Exception:
                logger.warning("Telegram update failed; retrying later")
            await asyncio.sleep(2)

    async def close(self):
        tasks = self.tasks + ([self.lyrics_task] if self.lyrics_task else [])
        tasks += list(self.lyrics.inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for track in list(self.lyrics.expiry_handles):
            self.lyrics.discard(track)


def create_app(settings=None, transport=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        # Fail early on the wrong encryption key rather than silently losing tokens.
        store = Store(settings.database, settings.encryption_key)
        store.get("tokens")
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            runtime = Runtime(settings, store, client)
            app.state.runtime = runtime
            runtime.tasks = [
                asyncio.create_task(runtime.poll_loop()),
                asyncio.create_task(runtime.telegram_loop()),
            ]
            try:
                yield
            finally:
                await runtime.close()
                store.close()

    app = FastAPI(
        title="Spotify Now Playing", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if (
            not request.url.path.startswith("/assets/")
            and request.url.path != "/api/v1/spotify/public/stream"
        ):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path in {"/setup", "/auth/spotify", "/auth/callback"}:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    def owner(key):
        if not secrets.compare_digest((key or "").encode(), settings.admin_key.encode()):
            raise HTTPException(401, "Invalid owner key")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/api/admin/status")
    async def status(request: Request, x_admin_key: str = Header(default="")):
        owner(x_admin_key)
        return {
            "connected": bool(request.app.state.runtime.store.get("tokens")),
            "telegram_enabled": bool(settings.telegram_token),
            "lyrics_enabled": bool(settings.lyrics_key),
        }

    @app.post("/auth/spotify")
    async def login(request: Request, admin_key: str = Form(max_length=512)):
        runtime = request.app.state.runtime
        now = time.monotonic()
        while runtime.login_attempts and runtime.login_attempts[0] < now - 60:
            runtime.login_attempts.popleft()
        if len(runtime.login_attempts) >= 10:
            raise HTTPException(429, "Too many attempts; try again in a minute")
        runtime.login_attempts.append(now)
        owner(admin_key)
        url, browser = runtime.spotify.authorize()
        response = RedirectResponse(url, status_code=303)
        response.set_cookie(
            "spotify_oauth",
            browser,
            max_age=600,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="lax",
            path="/auth",
        )
        return response

    @app.get("/auth/callback")
    async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        runtime = request.app.state.runtime
        try:
            verifier = runtime.spotify.consume_oauth(state, request.cookies.get("spotify_oauth", ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if error or not code:
            result = "denied"
        else:
            try:
                await runtime.spotify.connect(code, verifier)
            except UpstreamError:
                raise HTTPException(502, "Spotify login failed. Please start again.") from None
            runtime.publish({"success": False, "error": "connecting", "item": None})
            runtime.wake.set()
            result = "connected"
        response = RedirectResponse("/setup?spotify=" + result, status_code=303)
        response.delete_cookie(
            "spotify_oauth", path="/auth", secure=settings.secure_cookie, httponly=True, samesite="lax"
        )
        return response

    @app.post("/api/admin/disconnect")
    async def disconnect(request: Request, x_admin_key: str = Header(default="")):
        owner(x_admin_key)
        runtime = request.app.state.runtime
        await runtime.spotify.disconnect()
        if runtime.lyrics_task:
            runtime.lyrics_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runtime.lyrics_task
        for track in list(runtime.lyrics.cache):
            runtime.lyrics.discard(track)
        runtime.publish(playback(None))
        runtime.wake.set()
        return {"connected": False}

    @app.get("/api/v1/spotify/public/currently-playing")
    async def current(request: Request):
        return request.app.state.runtime.snapshot

    @app.get("/api/v1/spotify/public/stream")
    async def stream(request: Request):
        runtime = request.app.state.runtime
        if len(runtime.queues) >= 100:
            raise HTTPException(503, "Stream capacity reached")
        queue = asyncio.Queue(maxsize=2)
        runtime.queues.add(queue)

        async def events():
            try:
                yield "retry: 5000\n\n"
                yield "event: playing\ndata: " + json.dumps(runtime.snapshot, ensure_ascii=False) + "\n\n"
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=20)
                        yield "event: playing\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                runtime.queues.discard(queue)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"},
        )

    @app.get("/")
    @app.get("/widget")
    @app.get("/setup")
    async def frontend():
        if not (DIST / "index.html").is_file():
            raise HTTPException(503, "Build frontend first: cd frontend && npm ci && npm run build")
        return FileResponse(DIST / "index.html")

    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    return app


app = create_app()
