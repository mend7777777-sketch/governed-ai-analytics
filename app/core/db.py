"""Shared, bounded MySQL connection pool for application-owned queries."""

from __future__ import annotations

import os
from contextlib import contextmanager
from queue import Empty, Queue
from threading import Lock
from typing import Iterator

import pymysql

from app.core.config import required_env


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class DatabasePool:
    """Lazy fixed-size pool that bounds concurrent MySQL connections per process."""

    def __init__(self) -> None:
        self.size = max(1, int(os.getenv("DB_POOL_SIZE", "8")))
        self.acquire_timeout = max(1, int(os.getenv("DB_POOL_ACQUIRE_TIMEOUT_SECONDS", "10")))
        self._available: Queue = Queue(maxsize=self.size)
        self._created = 0
        self._lock = Lock()

    def _create(self):
        return pymysql.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=required_env("MYSQL_USER"),
            password=required_env("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE", "ai_analytics"),
            connect_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT_SECONDS", "10")),
            read_timeout=int(os.getenv("MYSQL_READ_TIMEOUT_SECONDS", "35")),
            write_timeout=int(os.getenv("MYSQL_WRITE_TIMEOUT_SECONDS", "35")),
            autocommit=False,
            ssl_disabled=_as_bool(os.getenv("MYSQL_SSL_DISABLED", "true"), True),
        )

    def acquire(self):
        try:
            connection = self._available.get_nowait()
        except Empty:
            with self._lock:
                if self._created < self.size:
                    self._created += 1
                    try:
                        return self._create()
                    except Exception:
                        self._created -= 1
                        raise
            try:
                connection = self._available.get(timeout=self.acquire_timeout)
            except Empty as exc:
                raise TimeoutError("数据库连接池已耗尽，请稍后重试。") from exc
        try:
            connection.ping(reconnect=True)
        except Exception:
            self.discard(connection)
            return self.acquire()
        return connection

    def release(self, connection) -> None:
        try:
            connection.rollback()
            self._available.put_nowait(connection)
        except Exception:
            self.discard(connection)

    def discard(self, connection) -> None:
        try:
            connection.close()
        finally:
            with self._lock:
                self._created = max(0, self._created - 1)

    @contextmanager
    def connection(self) -> Iterator:
        connection = self.acquire()
        try:
            yield connection
        except Exception:
            try:
                connection.rollback()
            finally:
                self.release(connection)
            raise
        else:
            self.release(connection)


pool = DatabasePool()


def db_connection():
    return pool.connection()


def query_timeout_ms() -> int:
    return max(1000, int(os.getenv("MYSQL_QUERY_TIMEOUT_MS", "30000")))
