import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.storage import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(
        client_id="test-client",
        admin_key="test-owner-" + "x" * 40,
        encryption_key=Fernet.generate_key().decode(),
        database=str(tmp_path / "state.sqlite3"),
        telegram_token="",
        telegram_chat="",
        telegram_language="en",
        lyrics_key="",
    )


@pytest.fixture
def store(settings):
    storage = Store(settings.database, settings.encryption_key)
    yield storage
    storage.close()


@pytest.fixture
def player():
    return {
        "is_playing": True,
        "progress_ms": 1200,
        "item": {
            "id": "A" * 22,
            "type": "track",
            "name": "Test <track>",
            "duration_ms": 60000,
            "artists": [{"name": "Artist & friends"}],
            "album": {"name": "Test album", "images": [{"url": "https://example.com/cover.jpg"}]},
        },
    }


@pytest.fixture
def mock_client():
    clients = []

    def build(handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    return build
