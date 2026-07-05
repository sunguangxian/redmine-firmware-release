"""跨进程 Release 发布锁。"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from .config_store import db


class PublishLockTimeout(RuntimeError):
    pass


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def publish_lock_ttl_seconds() -> float:
    return _env_float("RELEASE_TOOL_PUBLISH_LOCK_TTL", 15 * 60)


def publish_lock_wait_seconds() -> float:
    return _env_float("RELEASE_TOOL_PUBLISH_LOCK_WAIT", 120)


def _owner_id() -> str:
    return f"pid={os.getpid()};thread={threading.get_ident()};token={uuid.uuid4().hex}"


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publish_locks (
            lock_key TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            acquired_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_locks_expires ON publish_locks(expires_at)")


def _try_acquire(lock_key: str, owner: str, ttl_seconds: float) -> bool:
    now = time.time()
    with db() as conn:
        _ensure_table(conn)
        conn.execute("DELETE FROM publish_locks WHERE expires_at <= ?", (now,))
        try:
            conn.execute(
                """
                INSERT INTO publish_locks(lock_key, owner, acquired_at, expires_at)
                VALUES(?, ?, ?, ?)
                """,
                (lock_key, owner, now, now + ttl_seconds),
            )
        except sqlite3.IntegrityError:
            return False
    return True


def release_publish_lock(lock_key: str, owner: str) -> None:
    with db() as conn:
        _ensure_table(conn)
        conn.execute("DELETE FROM publish_locks WHERE lock_key = ? AND owner = ?", (lock_key, owner))


@contextmanager
def acquire_publish_lock(
    lock_key: str,
    *,
    owner: str | None = None,
    wait_seconds: float | None = None,
    ttl_seconds: float | None = None,
    poll_seconds: float = 0.2,
) -> Iterator[str]:
    normalized_key = (lock_key or "").strip().lower()
    if not normalized_key:
        raise PublishLockTimeout("发布锁 key 不能为空")
    actual_owner = owner or _owner_id()
    wait = publish_lock_wait_seconds() if wait_seconds is None else max(0.0, wait_seconds)
    ttl = publish_lock_ttl_seconds() if ttl_seconds is None else max(1.0, ttl_seconds)
    deadline = time.monotonic() + wait

    while True:
        if _try_acquire(normalized_key, actual_owner, ttl):
            break
        if time.monotonic() >= deadline:
            raise PublishLockTimeout("当前项目版本正在发布中，请稍后再试")
        time.sleep(max(0.01, min(poll_seconds, deadline - time.monotonic())))

    try:
        yield actual_owner
    finally:
        release_publish_lock(normalized_key, actual_owner)
