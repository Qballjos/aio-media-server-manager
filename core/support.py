"""Durable support threads scoped to a media account."""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

Owner = tuple[str, str, str]


class SupportReports:
    def __init__(self, config_dir: Path):
        self.path = config_dir / "support.db"

    @contextmanager
    def _database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, provider TEXT NOT NULL,
                    server_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    subject TEXT NOT NULL, message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY, report_id TEXT REFERENCES reports(id),
                    author TEXT NOT NULL, message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            yield db

    @staticmethod
    def _scope(owner: Owner | None) -> tuple[str, tuple]:
        return ("provider = ? AND server_id = ? AND account_id = ?", owner) if owner else ("1 = 1", ())

    def list(self, owner: Owner | None) -> list[dict]:
        clause, params = self._scope(owner)
        with self._database() as db:
            return [dict(row) for row in db.execute(
                f"""SELECT id, provider, account_id, subject, status, created_at
                    FROM reports WHERE {clause} ORDER BY created_at DESC, rowid DESC""",
                params,
            )]

    def create(self, owner: Owner, subject: str, message: str) -> str:
        report_id = uuid4().hex
        with self._database() as db:
            db.execute(
                "INSERT INTO reports(id, provider, server_id, account_id, subject, message) VALUES (?, ?, ?, ?, ?, ?)",
                (report_id, *owner, subject, message),
            )
        return report_id

    def detail(self, report_id: str, owner: Owner | None) -> dict | None:
        clause, params = self._scope(owner)
        with self._database() as db:
            report = db.execute(
                f"""SELECT id, provider, account_id, subject, message, status, created_at
                    FROM reports WHERE id = ? AND {clause}""",
                (report_id, *params),
            ).fetchone()
            if report is None:
                return None
            replies = db.execute(
                "SELECT id, author, message, created_at FROM replies WHERE report_id = ? ORDER BY id",
                (report_id,),
            )
            return {**dict(report), "replies": [dict(row) for row in replies]}

    def reply(self, report_id: str, owner: Owner | None, message: str) -> bool:
        clause, params = self._scope(owner)
        with self._database() as db:
            result = db.execute(
                f"""INSERT INTO replies(report_id, author, message)
                    SELECT id, ?, ? FROM reports WHERE id = ? AND {clause}""",
                ("member" if owner else "admin", message, report_id, *params),
            )
            return result.rowcount == 1

    def update_status(self, report_id: str, status: str) -> bool:
        with self._database() as db:
            return db.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id)).rowcount == 1
