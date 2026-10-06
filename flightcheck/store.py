from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import digest, now_iso


class RunStore:
    """Append-only through this API. Local SQLite is not a tamper-proof audit service."""
    def __init__(self, path=None, retention_days=None):
        self.path = Path(path or os.getenv("FLIGHTCHECK_DB", ".flightcheck/runs.sqlite3"))
        self.retention_days = int(retention_days if retention_days is not None else os.getenv("FLIGHTCHECK_RETENTION_DAYS", "7"))
        if self.retention_days < 1:
            raise ValueError("Retention must be at least one day")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)")
        self.path.chmod(0o600)
        self.purge_expired()

    def purge_expired(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self.connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, kind, title, result):
        self.purge_expired()
        # Real evidence stores statistics, not raw key/value witnesses. Synthetic demos stay inspectable.
        if kind in {"investigation", "reconcile"} and result.get("provenance") != "synthetic-executed":
            def redact(value):
                if isinstance(value, dict):
                    return {k: [] if k == "sample" else redact(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [redact(v) for v in value]
                return value
            result = {**redact(result), "samples_redacted": True}
        run_id = str(uuid.uuid4())
        payload = {**result, "id": run_id, "created_at": now_iso()}
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.connect() as conn:
            conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (run_id, payload["created_at"], kind, title, payload.get("status", "review"), encoded, digest(payload)))
        return payload

    def list(self):
        self.purge_expired()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT id, created_at, kind, title, status FROM runs ORDER BY rowid DESC LIMIT 100")]

    def get(self, run_id):
        self.purge_expired()
        with self.connect() as conn:
            row = conn.execute("SELECT payload, checksum FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        if digest(value) != row[1]:
            raise ValueError("Stored run checksum mismatch")
        return value
