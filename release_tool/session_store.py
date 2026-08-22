"""Encrypted SQLite-backed session storage shared by server workers."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator, MutableMapping, Optional

from .config_store import db
from .secret_store import protect_secret, unprotect_secret
from .session_config import SESSION_TTL_SECONDS


class SQLiteSessionStore:
    _SECRET_FIELDS = {"password", "api_key"}

    def _encode(self, session: dict[str, Any]) -> str:
        payload = {key: value for key, value in session.items() if not key.startswith("_session_")}
        for field in self._SECRET_FIELDS:
            if field in payload:
                payload[field] = protect_secret(str(payload.get(field) or ""))
        return json.dumps(payload, ensure_ascii=False)

    def _decode(self, payload: str) -> dict[str, Any]:
        try:
            session = json.loads(payload or "{}")
        except (TypeError, ValueError):
            return {}
        if not isinstance(session, dict):
            return {}
        for field in self._SECRET_FIELDS:
            if field in session:
                session[field] = unprotect_secret(str(session.get(field) or ""))
        return session

    def get(self, sid: str) -> Optional[dict[str, Any]]:
        if not sid:
            return None
        with db() as conn:
            row = conn.execute("SELECT payload FROM server_sessions WHERE sid = ?", (sid,)).fetchone()
        session = self._decode(row["payload"]) if row else {}
        return session or None

    def set(self, sid: str, session: dict[str, Any]) -> None:
        now = time.time()
        with db() as conn:
            conn.execute("DELETE FROM server_sessions WHERE updated_at < ?", (now - SESSION_TTL_SECONDS,))
            conn.execute(
                """
                INSERT INTO server_sessions(sid, payload, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(sid) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (sid, self._encode(session), now),
            )

    def delete(self, sid: str) -> None:
        with db() as conn:
            conn.execute("DELETE FROM server_sessions WHERE sid = ?", (sid,))

    def clear(self) -> None:
        with db() as conn:
            conn.execute("DELETE FROM server_sessions")

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with db() as conn:
            rows = conn.execute("SELECT sid, payload FROM server_sessions").fetchall()
        return {str(row["sid"]): self._decode(row["payload"]) for row in rows}


class SessionMapping(MutableMapping):
    """Compatibility mapping used by existing diagnostics and tests."""

    def __init__(self, store: SQLiteSessionStore):
        self.store = store

    def __getitem__(self, key: str) -> dict[str, Any]:
        value = self.store.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self.store.set(key, value)

    def __delitem__(self, key: str) -> None:
        if self.store.get(key) is None:
            raise KeyError(key)
        self.store.delete(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.store.snapshot())

    def __len__(self) -> int:
        return len(self.store.snapshot())

    def clear(self) -> None:
        self.store.clear()
