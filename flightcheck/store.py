from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

from .common import digest, now_iso


class RunStore:
    """Append-only through this API. Local SQLite is not a tamper-proof audit service."""
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("FLIGHTCHECK_DB", ".flightcheck/runs.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, kind, title, result):
        run_id = str(uuid.uuid4())
        payload = {**result, "id": run_id, "created_at": now_iso()}
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.connect() as conn:
            conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (run_id, payload["created_at"], kind, title, payload.get("status", "review"), encoded, digest(payload)))
        return payload

    def list(self):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT id, created_at, kind, title, status FROM runs ORDER BY rowid DESC LIMIT 100")]

    def get(self, run_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload, checksum FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        if digest(value) != row[1]:
            raise ValueError("Stored run checksum mismatch")
        return value
