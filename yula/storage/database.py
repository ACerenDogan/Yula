import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List


class DatabaseManager:
    """Yula yerel SQLite veritabanı yönetim sınıfı."""

    SESSION_STATUSES = {
        "PREPARING",
        "RUNNING",
        "STOPPED",
        "ERROR",
    }

    SESSION_TRANSITIONS = {
        "PREPARING": {"RUNNING", "STOPPED", "ERROR"},
        "RUNNING": {"STOPPED", "ERROR"},
        "STOPPED": set(),
        "ERROR": set(),
    }

    TARGET_TYPES = {
        "FILE",
        "DIRECTORY",
    }

    def __init__(self, db_path: str = "yula.db"):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    @contextmanager
    def _get_connection(
        self,
    ) -> Iterator[sqlite3.Connection]:
        """
        SQLite bağlantısını açar ve işlem bitince kesin olarak kapatır.

        İşlem başarılıysa commit, hatalıysa rollback yapılır.
        """
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")

        try:
            yield connection
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def _init_db(self) -> None:
        """
        Gerekli tabloları oluşturur ve eski veritabanlarını
        veri kaybetmeden güncel şemaya geçirir.
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitored_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    last_modified TEXT NOT NULL,

                    FOREIGN KEY (path_id)
                        REFERENCES monitored_paths(id)
                        ON DELETE CASCADE,

                    UNIQUE(path_id, file_path)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT,

                    status TEXT NOT NULL CHECK (
                        status IN (
                            'PREPARING',
                            'RUNNING',
                            'STOPPED',
                            'ERROR'
                        )
                    )
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    target_path TEXT NOT NULL,

                    target_type TEXT NOT NULL CHECK (
                        target_type IN ('FILE', 'DIRECTORY')
                    ),

                    FOREIGN KEY (session_id)
                        REFERENCES monitoring_sessions(id)
                        ON DELETE CASCADE,

                    UNIQUE(session_id, target_path)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    target_path TEXT,
                    description TEXT NOT NULL,
                    session_id INTEGER,

                    FOREIGN KEY (session_id)
                        REFERENCES monitoring_sessions(id)
                )
            """)

            event_columns = {
                row["name"]
                for row in cursor.execute(
                    "PRAGMA table_info(security_events)"
                ).fetchall()
            }

            if "session_id" not in event_columns:
                cursor.execute("""
                    ALTER TABLE security_events
                    ADD COLUMN session_id INTEGER
                    REFERENCES monitoring_sessions(id)
                """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_security_events_session_id
                ON security_events(session_id)
            """)

            connection.commit()

    def create_monitoring_session(
        self,
        targets: List[Dict[str, str]],
    ) -> int:
        """
        PREPARING durumunda yeni bir izleme oturumu oluşturur.

        Örnek targets:

        [
            {"path": "/project/app.py", "type": "FILE"},
            {"path": "/project/config", "type": "DIRECTORY"},
        ]
        """
        if not targets:
            raise ValueError(
                "İzleme oturumu için en az bir hedef gereklidir."
            )

        normalized_targets = []
        seen_paths = set()

        for target in targets:
            target_path = target.get("path")
            target_type = target.get("type", "").upper()

            if not isinstance(target_path, str) or not target_path.strip():
                raise ValueError(
                    "Her izleme hedefinin geçerli bir yolu olmalıdır."
                )

            if target_type not in self.TARGET_TYPES:
                raise ValueError(
                    "Hedef tipi FILE veya DIRECTORY olmalıdır."
                )

            normalized_path = os.path.abspath(
                os.path.expanduser(target_path)
            )

            if normalized_path in seen_paths:
                continue

            seen_paths.add(normalized_path)

            normalized_targets.append({
                "path": normalized_path,
                "type": target_type,
            })

        started_at = datetime.now().isoformat(
            timespec="milliseconds"
        )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO monitoring_sessions (
                    started_at,
                    stopped_at,
                    status
                )
                VALUES (?, NULL, 'PREPARING')
            """, (started_at,))

            session_id = cursor.lastrowid

            if session_id is None:
                raise RuntimeError(
                    "İzleme oturumu oluşturulamadı."
                )

            for target in normalized_targets:
                cursor.execute("""
                    INSERT INTO session_targets (
                        session_id,
                        target_path,
                        target_type
                    )
                    VALUES (?, ?, ?)
                """, (
                    session_id,
                    target["path"],
                    target["type"],
                ))

            connection.commit()
            return session_id

    def set_monitoring_session_status(
        self,
        session_id: int,
        new_status: str,
    ) -> None:
        """Oturum durumunu izin verilen geçişlere göre değiştirir."""
        normalized_status = new_status.upper()

        if normalized_status not in self.SESSION_STATUSES:
            raise ValueError(
                f"Geçersiz oturum durumu: {new_status}"
            )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT status
                FROM monitoring_sessions
                WHERE id = ?
            """, (session_id,))

            row = cursor.fetchone()

            if row is None:
                raise LookupError(
                    f"İzleme oturumu bulunamadı: {session_id}"
                )

            current_status = row["status"]

            if current_status == normalized_status:
                return

            allowed_transitions = self.SESSION_TRANSITIONS[
                current_status
            ]

            if normalized_status not in allowed_transitions:
                raise ValueError(
                    f"Geçersiz durum geçişi: "
                    f"{current_status} -> {normalized_status}"
                )

            stopped_at = None

            if normalized_status in {"STOPPED", "ERROR"}:
                stopped_at = datetime.now().isoformat(
                    timespec="milliseconds"
                )

            cursor.execute("""
                UPDATE monitoring_sessions
                SET
                    status = ?,
                    stopped_at = ?
                WHERE id = ?
            """, (
                normalized_status,
                stopped_at,
                session_id,
            ))

            connection.commit()

    def get_monitoring_session(
        self,
        session_id: int,
    ) -> Dict | None:
        """Oturumu ve oturumun izleme hedeflerini döndürür."""
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT *
                FROM monitoring_sessions
                WHERE id = ?
            """, (session_id,))

            session_row = cursor.fetchone()

            if session_row is None:
                return None

            cursor.execute("""
                SELECT
                    target_path,
                    target_type
                FROM session_targets
                WHERE session_id = ?
                ORDER BY id
            """, (session_id,))

            session = dict(session_row)
            session["targets"] = [
                dict(row)
                for row in cursor.fetchall()
            ]

            return session

    def add_monitored_path(self, path: str) -> int:
        """İzlenecek bir yolu kaydeder ve kayıt ID'sini döndürür."""
        absolute_path = os.path.abspath(path)
        created_at = datetime.now().isoformat(
            timespec="milliseconds"
        )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO monitored_paths (
                    path,
                    created_at
                )
                VALUES (?, ?)
            """, (
                absolute_path,
                created_at,
            ))

            cursor.execute("""
                SELECT id
                FROM monitored_paths
                WHERE path = ?
            """, (absolute_path,))

            row = cursor.fetchone()
            connection.commit()

            return row["id"] if row else -1

    def save_baseline_records(
        self,
        path_id: int,
        scan_results: Dict[str, dict],
    ) -> None:
        """Tarama sonuçlarını güvenilir baseline olarak kaydeder."""
        with self._get_connection() as connection:
            cursor = connection.cursor()

            for file_path, data in scan_results.items():
                cursor.execute("""
                    INSERT INTO file_baselines (
                        path_id,
                        file_path,
                        sha256_hash,
                        file_size,
                        last_modified
                    )
                    VALUES (?, ?, ?, ?, ?)

                    ON CONFLICT(path_id, file_path)
                    DO UPDATE SET
                        sha256_hash = excluded.sha256_hash,
                        file_size = excluded.file_size,
                        last_modified = excluded.last_modified
                """, (
                    path_id,
                    file_path,
                    data["hash"],
                    data["size"],
                    str(data["last_modified"]),
                ))

            connection.commit()

    def get_baseline_for_path(
        self,
        path_id: int,
    ) -> Dict[str, str]:
        """Kayıtlı baseline hash değerlerini döndürür."""
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    file_path,
                    sha256_hash
                FROM file_baselines
                WHERE path_id = ?
            """, (path_id,))

            return {
                row["file_path"]: row["sha256_hash"]
                for row in cursor.fetchall()
            }

    def log_security_event(
        self,
        event_type: str,
        risk_level: str,
        target_path: str,
        description: str,
        session_id: int | None = None,
    ) -> int:
        """Güvenlik olayını kaydeder ve olay ID'sini döndürür."""
        timestamp = datetime.now().isoformat(
            timespec="milliseconds"
        )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO security_events (
                    timestamp,
                    event_type,
                    risk_level,
                    target_path,
                    description,
                    session_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                event_type,
                risk_level,
                target_path,
                description,
                session_id,
            ))

            connection.commit()
            return cursor.lastrowid

    def get_recent_events(
        self,
        limit: int = 20,
        session_id: int | None = None,
    ) -> List[Dict]:
        """En son güvenlik olaylarını döndürür."""
        with self._get_connection() as connection:
            cursor = connection.cursor()

            if session_id is None:
                cursor.execute("""
                    SELECT *
                    FROM security_events
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT *
                    FROM security_events
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    session_id,
                    limit,
                ))

            return [
                dict(row)
                for row in cursor.fetchall()
            ]