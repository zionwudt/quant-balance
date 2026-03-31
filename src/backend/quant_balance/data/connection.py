"""SQLite 连接管理器 — 线程安全的单例连接池。

每个 (db_path,) 维护一个连接，避免频繁开关。
线程安全：使用 threading.local 确保每个线程持有独立连接。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from quant_balance.data.common import CACHE_DB_PATH

_local = threading.local()
_lock = threading.Lock()


def get_shared_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """获取当前线程的共享 SQLite 连接。

    首次调用时创建连接并启用 WAL，后续复用。
    """
    path = str(db_path or CACHE_DB_PATH)

    conns: dict[str, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    if not hasattr(_local, "conns"):
        _local.conns = conns

    conn = conns.get(path)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.Error:
            conns.pop(path, None)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conns[path] = conn
    return conn


def close_all_connections() -> None:
    """关闭当前线程的所有共享连接（用于 shutdown）。"""
    conns: dict[str, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    for conn in conns.values():
        try:
            conn.close()
        except sqlite3.Error:
            pass
    conns.clear()


__all__ = ["get_shared_connection", "close_all_connections"]
