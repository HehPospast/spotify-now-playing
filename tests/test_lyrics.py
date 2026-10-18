import asyncio

import httpx
import pytest

from app.lyrics import SpicyLyricsService, normalize_response

TRACK = "A" * 22


def envelope(source="spotify"):
    return {
        "Status": 200,
        "Body": {
            "id": TRACK,
            "Type": "Line",
            "source": source,
            "Content": [{"Type": "Vocal", "StartTime": 1, "EndTime": 3, "Text": "Synthetic\u200b"}],
        },
    }


def test_normalization_preserves_timings_and_marks():
    result = normalize_response(envelope(), TRACK)
    assert result["lines"] == [{"start_ms": 1000, "end_ms": 3000, "text": "Synthetic\u200b"}]
    assert result["source"]["name"] == "Spotify"


def test_community_requires_attribution():
    data = envelope("spicy_lyrics")
    with pytest.raises(ValueError):
        normalize_response(data, TRACK)
    data["Body"]["UploadAttribution"] = {
        "Uploader": {"username": "tester", "url": "https://example.com/tester"}
    }
    assert normalize_response(data, TRACK)["credits"][0]["name"] == "uploader: tester"


def test_singleflight_expiry_and_no_disk_cache():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            assert request.headers["Authorization"] == "Bearer test-key"
            return httpx.Response(200, json=envelope())

        clock = [0]
        service = SpicyLyricsService(
            secret_key="test-key",
            clock=lambda: clock[0],
            ttl=10,
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        results = await asyncio.gather(service.get(TRACK), service.get(TRACK))
        assert len(calls) == 1 and results[0] == results[1]
        clock[0] = 11
        assert service.peek(TRACK) is None

    asyncio.run(run())
