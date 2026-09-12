"""
MemoryService — session/conversation/learning/quiz/preference memory.

Storage layer is intentionally swappable: `SQLiteStorage` is used by default
(zero-config, file-based, fine for a prototype and small deployments). Swap
it out for a different `Storage` implementation (Postgres, Redis, ...) by
changing `get_storage()` — nothing else in the app needs to change.

Never store passwords or API keys here — only learning-related state.
"""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("MEMORY_DB_PATH", BASE_DIR / "data" / "memory.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = Lock()


def _default_memory() -> dict:
    return {
        "userName": None,
        "lang": "id",
        "activeTopic": None,
        "activeSection": None,
        "instructionStyle": {},
        "conversationSummary": None,
        "messages": [],          # capped rolling window of {role, content, ts}
        "quizHistory": None,     # last completed quiz summary
        "quizStats": {},         # per-section wrong-answer counters, for adaptive learning
        "createdAt": time.time(),
        "updatedAt": time.time(),
    }


class SQLiteStorage:
    def __init__(self, path: Path):
        self.path = str(path)
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )

    def _conn(self):
        return sqlite3.connect(self.path)

    def get(self, session_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT data FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, session_id: str, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                """INSERT INTO sessions(session_id, data, updated_at) VALUES(?,?,?)
                   ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
                (session_id, payload, time.time()),
            )

    def delete(self, session_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))


_storage = SQLiteStorage(DB_PATH)


def get_storage():
    return _storage


def new_session_id() -> str:
    return uuid.uuid4().hex


def get_memory(session_id: str) -> dict:
    with _lock:
        data = _storage.get(session_id)
        if data is None:
            data = _default_memory()
            _storage.set(session_id, data)
        return data


def save_memory(session_id: str, memory: dict):
    memory["updatedAt"] = time.time()
    with _lock:
        _storage.set(session_id, memory)


def reset_memory(session_id: str):
    with _lock:
        _storage.set(session_id, _default_memory())


def delete_memory(session_id: str):
    with _lock:
        _storage.delete(session_id)


def append_message(memory: dict, role: str, content: str, meta: Optional[dict] = None):
    entry = {"role": role, "content": content, "ts": time.time()}
    if meta:
        entry.update(meta)
    memory["messages"].append(entry)
    # cap the rolling window, same 40-message cap the frontend used
    if len(memory["messages"]) > 40:
        removed_count = len(memory["messages"]) - 40
        memory["messages"] = memory["messages"][removed_count:]
        topic = memory.get("activeTopic") or "berbagai topik Laboratorium Maya"
        memory["conversationSummary"] = f"Percakapan sebelumnya membahas: {topic}."


def record_wrong_topic(memory: dict, section_title: str):
    stats = memory.setdefault("quizStats", {})
    stats[section_title] = stats.get(section_title, 0) + 1
