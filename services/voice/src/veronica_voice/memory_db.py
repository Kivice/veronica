"""SQLite + FTS5 Persistent Tactical Memory Bank for Project Veronica (Roadmap P5).

Provides full-text search (FTS5), key-value storage, JSON backward compatibility,
export, and secure wipe with VACUUM so no deleted rows remain in the database file.
"""
from __future__ import annotations

import base64
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

MEMORY_DIR = Path.home() / ".veronica"
MEMORY_DB_FILE = MEMORY_DIR / "memory.db"
MEMORY_JSON_FILE = MEMORY_DIR / "memory.json"


class TacticalMemoryBank:
    """SQLite + FTS5 backed memory store with automatic JSON mirror for backward compatibility."""

    def __init__(self, db_path: Optional[Path] = None, json_path: Optional[Path] = None):
        self.db_path = db_path or MEMORY_DB_FILE
        self.json_path = json_path or MEMORY_JSON_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_from_json_if_needed()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=DELETE;")
            conn.execute("PRAGMA secure_delete=ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    key TEXT PRIMARY KEY,
                    value_b64 TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            # FTS5 virtual table for fast full-text recall across keys and values
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    key,
                    value
                )
                """
            )
            conn.commit()

    @staticmethod
    def _encode(val: Any) -> str:
        raw = json.dumps(val, ensure_ascii=False)
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode(val_b64: str) -> Any:
        try:
            raw = base64.b64decode(val_b64.encode("ascii")).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return val_b64

    def _migrate_from_json_if_needed(self) -> None:
        if not self.json_path.exists():
            return
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
            notes = data.get("notes", {})
            if isinstance(notes, dict) and notes:
                existing = self.list_all()
                for k, v in notes.items():
                    if k not in existing:
                        self.set(k, v, sync_json=False)
        except Exception:
            pass

    def _sync_to_json(self, notes: dict[str, Any]) -> None:
        try:
            doc = {
                "name": "Veronica",
                "role": "Tactical Desktop Assistant",
                "notes": notes,
                "preferences": {"voice": "en-US-AvaNeural", "theme": "ironman-tactical"},
            }
            if self.json_path.exists():
                try:
                    current = json.loads(self.json_path.read_text(encoding="utf-8"))
                    if isinstance(current, dict):
                        current["notes"] = notes
                        doc = current
                except Exception:
                    pass
            self.json_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set(self, key: str, value: Any, sync_json: bool = True) -> dict[str, Any]:
        clean_key = key.strip()
        now = time.time()
        encoded = self._encode(value)
        str_val = str(value)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memories (key, value_b64, updated_at) VALUES (?, ?, ?)",
                (clean_key, encoded, now),
            )
            conn.execute("DELETE FROM memories_fts WHERE key = ?", (clean_key,))
            conn.execute(
                "INSERT INTO memories_fts (key, value) VALUES (?, ?)",
                (clean_key, str_val),
            )
            conn.commit()
        notes = self.list_all()
        if sync_json:
            self._sync_to_json(notes)
        return notes

    def get(self, key: str) -> Any:
        clean_key = key.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_b64 FROM memories WHERE key = ?", (clean_key,)
            ).fetchone()
            if row:
                return self._decode(row["value_b64"])
            # Case-insensitive fallback
            row_ci = conn.execute(
                "SELECT value_b64 FROM memories WHERE lower(key) = lower(?)", (clean_key,)
            ).fetchone()
            if row_ci:
                return self._decode(row_ci["value_b64"])
        return None

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Full-text search across stored memories using SQLite FTS5 with substring fallback."""
        clean_q = query.strip()
        if not clean_q:
            return self.list_all()

        results: dict[str, Any] = {}
        # Sanitize FTS5 query tokens
        tokens = [t for t in clean_q.replace('"', "").replace("'", "").split() if t.isalnum()]
        if tokens:
            fts_query = " OR ".join(f'"{t}"*' for t in tokens)
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT key FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                        (fts_query, limit),
                    ).fetchall()
                    for r in rows:
                        k = r["key"]
                        val = self.get(k)
                        if val is not None:
                            results[k] = val
            except Exception:
                pass

        # Substring fallback if FTS returned nothing
        if not results:
            q_lower = clean_q.lower()
            for k, v in self.list_all().items():
                if q_lower in k.lower() or q_lower in str(v).lower():
                    results[k] = v
                    if len(results) >= limit:
                        break
        return results

    def delete(self, key: str) -> dict[str, Any]:
        clean_key = key.strip()
        with self._connect() as conn:
            conn.execute("DELETE FROM memories WHERE lower(key) = lower(?)", (clean_key,))
            conn.execute("DELETE FROM memories_fts WHERE lower(key) = lower(?)", (clean_key,))
            conn.commit()
        notes = self.list_all()
        self._sync_to_json(notes)
        return notes

    def list_all(self) -> dict[str, Any]:
        notes: dict[str, Any] = {}
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT key, value_b64 FROM memories ORDER BY updated_at ASC"
                ).fetchall()
                for r in rows:
                    notes[r["key"]] = self._decode(r["value_b64"])
        except Exception:
            pass
        return notes

    def wipe(self) -> None:
        """Securely wipe all memories and VACUUM the database so no recoverable rows remain."""
        with self._connect() as conn:
            conn.execute("DELETE FROM memories")
            conn.execute("DELETE FROM memories_fts")
            conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
            conn.commit()
        # VACUUM must run outside an open transaction
        conn = self._connect()
        try:
            conn.isolation_level = None
            conn.execute("PRAGMA secure_delete=ON;")
            conn.execute("VACUUM;")
        finally:
            conn.close()
        self._sync_to_json({})

