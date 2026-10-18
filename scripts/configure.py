import base64
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists; edit it directly. Existing secrets were preserved.")
source = (root / ".env.example").read_text(encoding="utf-8")
source = source.replace("replace-with-random-owner-key", secrets.token_urlsafe(48))
source = source.replace("replace-with-fernet-key", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
target.write_text(source, encoding="utf-8")
print("Created .env. Set SPOTIFY_CLIENT_ID before starting the app.")
