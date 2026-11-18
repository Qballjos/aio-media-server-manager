"""Persistent AIO access grants for accounts imported into Seerr."""

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
            yield db

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
