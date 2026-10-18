from __future__ import annotations

import asyncio
import math
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

API_URL = "https://api.spicylyrics.org/v1/lyrics/"
TRACK_ID = re.compile(r"[A-Za-z0-9]{22}\Z")


def state(track_id, status="unavailable"):
    return {"track_id": track_id, "status": status}


def milliseconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(value * 1000) if math.isfinite(value) and value >= 0 else None


def interval(raw):
    start, end = milliseconds(raw.get("StartTime")), milliseconds(raw.get("EndTime"))
    if start is None or end is None or end <= start:
        raise ValueError("Invalid vocal interval")
    return {"start_ms": start, "end_ms": end}


def vocal_group(group, role, opposite):
    timing = interval(group)
    raw_syllables = group["Syllables"]
    syllables = []
    for index, raw in enumerate(raw_syllables):
        text = raw["Text"]  # Preserve invisible provenance marks and original text.
        if not isinstance(text, str):
            raise ValueError("Invalid syllable text")
        if index < len(raw_syllables) - 1 and not raw.get("IsPartOfWord", False):
            text += " "
        syllable = {"text": text, **interval(raw)}
        if (
            syllable["start_ms"] < timing["start_ms"]
            or syllable["end_ms"] > timing["end_ms"]
            or (syllables and syllable["start_ms"] < syllables[-1]["end_ms"])
        ):
            raise ValueError("Invalid syllable boundaries")
        syllables.append(syllable)
    if not syllables:
        raise ValueError("Empty vocal group")
    return {
        **timing,
        "text": "".join(s["text"] for s in syllables),
        "syllables": syllables,
        "vocal_role": role,
        "opposite_aligned": opposite,
    }


def normalize_response(envelope, track_id):
    if envelope.get("Status") != 200:
        raise ValueError("Unexpected envelope status")
    body = envelope["Body"]
    if body.get("id") != track_id:
        raise ValueError("Track mismatch")
    kind = body["Type"]
    lines = []
    if kind == "Static":
        for raw in body["Lines"]:
            if not isinstance(raw["Text"], str):
                raise ValueError("Invalid static text")
            lines.append({"text": raw["Text"]})
    elif kind in ("Line", "Syllable"):
        for raw in body["Content"]:
            if raw.get("Type") != "Vocal":
                continue  # Instrumental gaps are not fabricated vocal lines.
            if kind == "Line":
                if not isinstance(raw["Text"], str):
                    raise ValueError("Invalid line text")
                lines.append({**interval(raw), "text": raw["Text"]})
            else:
                opposite = bool(raw.get("OppositeAligned", False))
                lead = vocal_group(raw["Lead"], "lead", opposite)
                background = [
                    vocal_group(group, "background", opposite) for group in raw.get("Background", [])
                ]
                if background:
                    lead["background"] = background
                lines.append(lead)
        lines.sort(key=lambda line: line["start_ms"])
    else:
        raise ValueError("Unknown sync type")
    if not lines:
        return state(track_id)

    provider = body.get("source", "unknown")
    sources = {
        "spicy_lyrics": {"name": "Spicy Lyrics", "url": "https://spicylyrics.org/"},
        "apple_music": {"name": "Apple Music", "url": "https://music.apple.com/"},
        "spotify": {"name": "Spotify", "url": "https://open.spotify.com/"},
    }
    credits = []
    attribution = body.get("UploadAttribution", {})
    if provider == "spicy_lyrics":
        # Never display community lyrics without the mandatory uploader credit.
        for role in ("Uploader", "Maker"):
            contributor = attribution.get(role)
            if role == "Maker" and contributor is None:
                continue
            if not contributor or not contributor.get("username") or not contributor.get("url"):
                raise ValueError("Missing community credit")
            url = urlparse(contributor["url"])
            if url.scheme not in ("https", "http") or not url.netloc:
                raise ValueError("Invalid community credit URL")
            credits.append({"name": f"{role.lower()}: {contributor['username']}", "url": contributor["url"]})
    return {
        "track_id": track_id,
        "status": "ready",
        "sync_type": {"Static": "none", "Line": "line", "Syllable": "syllable"}[kind],
        "offset_ms": 0,
        "source": sources.get(provider, {"name": "source unknown", "url": None}),
        "credits": credits,
        "lines": lines,
        "provenance": {
            "provider": provider,
            "songwriters": body.get("SongWriters", []),
            "upload_attribution": attribution,
        },
    }


def retry_after(value):
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 60.0
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            return max(0, (date - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 60.0


class SpicyLyricsService:
    def __init__(self, client_factory=None, clock=time.monotonic, ttl=86400, secret_key=""):
        self.secret_key = secret_key
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=8.0))
        self.clock = clock
        self.ttl = min(max(ttl, 1), 86400)
        self.cache = {}
        self.inflight = {}
        self.expiry_handles = {}
        self.retry_at = 0.0

    def discard(self, track_id):
        self.cache.pop(track_id, None)
        handle = self.expiry_handles.pop(track_id, None)
        if handle:
            handle.cancel()

    def peek(self, track_id):
        cached = self.cache.get(track_id)
        if cached and cached[0] > self.clock():
            return deepcopy(cached[1])
        self.discard(track_id)
        return None

    def expires_at(self, track_id):
        cached = self.cache.get(track_id)
        return cached[0] if cached else self.clock()

    async def get(self, track_id):
        if not self.secret_key or not TRACK_ID.fullmatch(track_id or ""):
            return state(track_id)
        cached = self.peek(track_id)
        if cached is not None:
            return cached
        if track_id not in self.inflight:
            task = asyncio.create_task(self._fetch_and_cache(track_id))
            self.inflight[track_id] = task
            task.add_done_callback(lambda done: self.inflight.pop(track_id, None))
        return deepcopy(await asyncio.shield(self.inflight[track_id]))

    async def _fetch_and_cache(self, track_id):
        result, original = state(track_id, "error"), None
        if self.clock() < self.retry_at:
            return result
        try:
            async with self.client_factory() as client:
                for attempt in range(3):
                    if self.clock() < self.retry_at:
                        break
                    try:
                        response = await client.get(
                            API_URL + track_id,
                            headers={"Authorization": f"Bearer {self.secret_key}"},
                        )
                    except httpx.RequestError:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * 2**attempt)
                        continue
                    if response.status_code == 429:
                        # Application-wide cooldown; never shorten Retry-After.
                        self.retry_at = self.clock() + retry_after(response.headers.get("Retry-After"))
                        break
                    if response.status_code == 404:
                        result = state(track_id)
                        break
                    if response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * 2**attempt)
                        continue
                    if response.status_code != 200:
                        break
                    original = response.json()
                    result = normalize_response(original, track_id)
                    break
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError, httpx.HTTPError):
            # Do not log headers, payloads, request objects, secrets or upstream messages.
            original = None
            result = state(track_id, "error")
        ttl = self.ttl if result["status"] == "ready" else 60
        if len(self.cache) >= 128:
            self.discard(next(iter(self.cache)))
        self.cache[track_id] = (self.clock() + ttl, result, original)
        self.expiry_handles[track_id] = asyncio.get_running_loop().call_later(ttl, self.discard, track_id)
        return result
