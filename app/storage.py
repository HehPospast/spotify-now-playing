import json
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet


class Store:
    def __init__(self, path, key):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value BLOB NOT NULL)")
        self.cipher = Fernet(key.encode())

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else default

    def set(self, key, value):
        data = self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode())
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, data))

    def delete(self, key):
        with self.db:
            self.db.execute("DELETE FROM state WHERE key = ?", (key,))

    def close(self):
        self.db.close()
