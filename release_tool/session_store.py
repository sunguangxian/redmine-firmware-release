"""Session storage abstraction.

The current implementation intentionally remains in-memory so Redmine
password/API key values are not persisted across process restarts.
"""

from __future__ import annotations

from typing import Any, MutableMapping, Optional


class InMemorySessionStore:
    def __init__(self, backing: MutableMapping[str, dict[str, Any]]):
        self._backing = backing

    def get(self, sid: str) -> Optional[dict[str, Any]]:
        return self._backing.get(sid)

    def set(self, sid: str, session: dict[str, Any]) -> None:
        self._backing[sid] = session

    def delete(self, sid: str) -> None:
        self._backing.pop(sid, None)
