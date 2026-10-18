import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    client_id: str = field(default_factory=lambda: os.getenv("SPOTIFY_CLIENT_ID", "").strip())
    redirect_uri: str = field(
        default_factory=lambda: os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8080/auth/callback"
        ).strip()
    )
    admin_key: str = field(default_factory=lambda: os.getenv("ADMIN_KEY", ""))
    encryption_key: str = field(default_factory=lambda: os.getenv("TOKEN_ENCRYPTION_KEY", ""))
    database: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "data/state.sqlite3"))
    poll_seconds: float = field(default_factory=lambda: float(os.getenv("POLL_INTERVAL_SECONDS", "10")))
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    telegram_chat: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip())
    lyrics_key: str = field(default_factory=lambda: os.getenv("SPICY_LYRICS_SECRET_KEY", "").strip())

    @property
    def secure_cookie(self):
        return self.redirect_uri.startswith("https://")

    def validate(self):
        if len(self.admin_key) < 32:
            raise ValueError("ADMIN_KEY must contain at least 32 characters; run scripts/configure.py")
        Fernet(self.encryption_key.encode())
        url = urlsplit(self.redirect_uri)
        if (
            url.path != "/auth/callback"
            or url.query
            or url.fragment
            or url.username
            or not url.hostname
            or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "::1"}))
        ):
            raise ValueError("Use an HTTPS /auth/callback URI, or HTTP with 127.0.0.1 / [::1]")
        if not self.client_id:
            raise ValueError("Set SPOTIFY_CLIENT_ID in .env")
        if not 5 <= self.poll_seconds <= 300:
            raise ValueError("POLL_INTERVAL_SECONDS must be between 5 and 300")
        if bool(self.telegram_token) != bool(self.telegram_chat):
            raise ValueError("Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or neither")
