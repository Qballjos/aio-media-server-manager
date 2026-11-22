"""Persistent AIO access grants for accounts imported into Seerr."""

import json
import secrets
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path


class MediaUsers:
    def __init__(self, config_dir: Path):
        self.path = config_dir / "media-users.db"

    @contextmanager
    def _database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS grants (
                    provider TEXT NOT NULL, server_id TEXT NOT NULL,
                    account_id TEXT NOT NULL, version TEXT NOT NULL,
                    PRIMARY KEY (provider, server_id, account_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    provider TEXT NOT NULL, server_id TEXT NOT NULL,
                    account_id TEXT NOT NULL, display_name TEXT NOT NULL,
                    PRIMARY KEY (provider, server_id, account_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS avatars (
                    provider TEXT NOT NULL, server_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    data BLOB NOT NULL, mime TEXT NOT NULL, version TEXT NOT NULL,
                    PRIMARY KEY (provider, server_id, account_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS streaming_preferences (
                    provider TEXT NOT NULL, server_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    country TEXT NOT NULL, provider_ids TEXT NOT NULL,
                    PRIMARY KEY (provider, server_id, account_id)
                )
            """)
            yield db

    def streaming(self, account: tuple[str, str, str]) -> tuple[str, list[int]]:
        if not self.path.is_file():
            return "", []
        with self._database() as db:
            row = db.execute(
                "SELECT country, provider_ids FROM streaming_preferences "
                "WHERE provider = ? AND server_id = ? AND account_id = ?",
                account,
            ).fetchone()
            return (row[0], json.loads(row[1])) if row else ("", [])

    def set_streaming(self, account: tuple[str, str, str], country: str, provider_ids: list[int]) -> None:
        with self._database() as db:
            db.execute(
                "INSERT INTO streaming_preferences VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, server_id, account_id) DO UPDATE SET "
                "country = excluded.country, provider_ids = excluded.provider_ids",
                (*account, country, json.dumps(provider_ids)),
            )

    def display_name(self, account: tuple[str, str, str]) -> str:
        with self._database() as db:
            row = db.execute(
                "SELECT display_name FROM profiles WHERE provider = ? AND server_id = ? AND account_id = ?",
                account,
            ).fetchone()
            return row[0] if row else ""

    def set_display_name(self, account: tuple[str, str, str], name: str) -> None:
        with self._database() as db:
            db.execute(
                "INSERT INTO profiles VALUES (?, ?, ?, ?) "
                "ON CONFLICT(provider, server_id, account_id) DO UPDATE SET display_name = excluded.display_name",
                (*account, name),
            )

    def avatar_version(self, account: tuple[str, str, str]) -> str | None:
        with self._database() as db:
            row = db.execute(
                "SELECT version FROM avatars WHERE provider = ? AND server_id = ? AND account_id = ?",
                account,
            ).fetchone()
            return row[0] if row else None

    def avatar(self, account: tuple[str, str, str]) -> tuple[bytes, str] | None:
        with self._database() as db:
            return db.execute(
                "SELECT data, mime FROM avatars WHERE provider = ? AND server_id = ? AND account_id = ?",
                account,
            ).fetchone()

    def set_avatar(self, account: tuple[str, str, str], data: bytearray, mime: str) -> str:
        version = secrets.token_hex(12)
        with self._database() as db:
            db.execute(
                "INSERT INTO avatars VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, server_id, account_id) DO UPDATE SET "
                "data = excluded.data, mime = excluded.mime, version = excluded.version",
                (*account, data, mime, version),
            )
        return version

    def clear_avatar(self, account: tuple[str, str, str]) -> None:
        with self._database() as db:
            db.execute(
                "DELETE FROM avatars WHERE provider = ? AND server_id = ? AND account_id = ?",
                account,
            )

    def grant(self, provider: str, server_id: str, account_id: str) -> str:
        with self._database() as db:
            db.execute(
                "INSERT OR IGNORE INTO grants VALUES (?, ?, ?, ?)",
                (provider, server_id, account_id, secrets.token_urlsafe(32)),
            )
            return db.execute(
                "SELECT version FROM grants WHERE provider = ? AND server_id = ? AND account_id = ?",
                (provider, server_id, account_id),
            ).fetchone()[0]

    def versions(self, provider: str, server_id: str) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        with self._database() as db:
            return dict(db.execute(
                "SELECT account_id, version FROM grants WHERE provider = ? AND server_id = ?",
                (provider, server_id),
            ))

    def version(self, provider: str, server_id: str, account_id: str) -> str | None:
        if not self.path.is_file():
            return None
        with self._database() as db:
            row = db.execute(
                "SELECT version FROM grants WHERE provider = ? AND server_id = ? AND account_id = ?",
                (provider, server_id, account_id),
            ).fetchone()
            return row[0] if row else None

    def revoke(self, provider: str, server_id: str, account_id: str) -> None:
        with self._database() as db:
            db.execute(
                "DELETE FROM grants WHERE provider = ? AND server_id = ? AND account_id = ?",
                (provider, server_id, account_id),
            )
