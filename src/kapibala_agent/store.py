from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from .domain import Session, SessionStatus


class SessionStore:
    """SQLite-backed session authority.

    The rate-limit reservation is committed before the external send. This is
    deliberately fail-closed: a transport failure may consume one 60-second
    slot, but can never create a duplicate-send window.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._schema_lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._schema_lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    customer_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    anomaly_count INTEGER NOT NULL CHECK (anomaly_count >= 0),
                    last_sent_at REAL,
                    updated_at REAL NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS REAL))
                )
                """
            )

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _from_row(customer_id: str, row: sqlite3.Row | None) -> Session:
        if row is None:
            return Session(customer_id=customer_id)
        return Session(
            customer_id=customer_id,
            status=SessionStatus(row["status"]),
            anomaly_count=int(row["anomaly_count"]),
            last_sent_at=row["last_sent_at"],
        )

    def get(self, customer_id: str) -> Session:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, anomaly_count, last_sent_at FROM sessions WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
        return self._from_row(customer_id, row)

    def save(self, session: Session) -> None:
        with self._immediate() as connection:
            connection.execute(
                """
                INSERT INTO sessions(customer_id, status, anomaly_count, last_sent_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    status = excluded.status,
                    anomaly_count = excluded.anomaly_count,
                    last_sent_at = COALESCE(excluded.last_sent_at, sessions.last_sent_at),
                    updated_at = CAST(strftime('%s', 'now') AS REAL)
                """,
                (
                    session.customer_id,
                    session.status.value,
                    session.anomaly_count,
                    session.last_sent_at,
                ),
            )

    def reactivate(self, customer_id: str) -> Session:
        with self._immediate() as connection:
            connection.execute(
                """
                INSERT INTO sessions(customer_id, status, anomaly_count)
                VALUES (?, ?, 0)
                ON CONFLICT(customer_id) DO UPDATE SET
                    status = excluded.status,
                    anomaly_count = 0,
                    updated_at = CAST(strftime('%s', 'now') AS REAL)
                """,
                (customer_id, SessionStatus.ACTIVE.value),
            )
        return self.get(customer_id)

    def reserve_send(self, customer_id: str, now: float, window_seconds: float) -> bool:
        """Atomically reserve the one allowed send slot for a rolling window."""
        with self._immediate() as connection:
            row = connection.execute(
                "SELECT status, last_sent_at FROM sessions WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
            if row is None or SessionStatus(row["status"]) is not SessionStatus.ACTIVE:
                return False

            last_sent_at = row["last_sent_at"]
            if last_sent_at is not None and now - float(last_sent_at) < window_seconds:
                return False

            connection.execute(
                """
                UPDATE sessions
                SET last_sent_at = ?, updated_at = CAST(strftime('%s', 'now') AS REAL)
                WHERE customer_id = ?
                """,
                (now, customer_id),
            )
            return True
