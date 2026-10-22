"""Smoke-test a running installation without credentials or real provider calls."""

import argparse
import json
import re
import time
from urllib.error import URLError
from urllib.request import urlopen


def check(base_url):
    base_url = base_url.rstrip("/")
    for attempt in range(30):
        try:
            with urlopen(base_url + "/healthz", timeout=2) as response:
                assert json.load(response) == {"status": "ok"}
            break
        except (URLError, TimeoutError):
            if attempt == 29:
                raise
            time.sleep(1)

    for path in ("/setup", "/widget"):
        with urlopen(base_url + path, timeout=5) as response:
            assert response.headers.get_content_type() == "text/html", path
            html = response.read().decode()
        assets = re.findall(r'(?:src|href)="(/assets/[^"<>]+)"', html)
        assert assets, f"No built assets in {path}"
        for asset in assets:
            with urlopen(base_url + asset, timeout=5) as response:
                assert response.headers.get_content_type() in {
                    "text/javascript",
                    "application/javascript",
                    "text/css",
                }, asset
                assert response.read(), f"Empty asset: {asset}"

    with urlopen(base_url + "/api/v1/spotify/public/currently-playing", timeout=5) as response:
        assert "item" in json.load(response)

    with urlopen(base_url + "/api/v1/spotify/public/stream", timeout=5) as response:
        assert response.headers.get_content_type() == "text/event-stream"
        assert response.readline().strip() == b"retry: 5000"
        assert response.readline().strip() == b""
        assert response.readline().strip() == b"event: playing"
        line = response.readline().decode()
        assert line.startswith("data: ")
        assert "item" in json.loads(line.removeprefix("data: "))

    print("Deployment OK: health, setup, widget, built assets, playback JSON and SSE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Installation URL, e.g. http://127.0.0.1:8080")
    check(parser.parse_args().base_url)
