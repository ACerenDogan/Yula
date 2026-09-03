import os
import sqlite3
from datetime import datetime
from typing import Dict, List


class DatabaseManager:
    """
    Yula yerel SQLite veritabanı yönetim sınıfı.

    İzlenen yolları, baseline kayıtlarını, izleme oturumlarını
    ve güvenlik olaylarını saklar.
    """

    def __init__(self, db_path: str = "yula.db"):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Yeni bir SQLite bağlantısı oluşturur.

        foreign_keys:
            SQLite foreign key kontrollerini etkinleştirir.

        busy_timeout:
            Başka bir işlem veritabanını kullanıyorsa hemen hata vermek
            yerine beş saniyeye kadar bekler.
        """
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _init_db(self) -> None:
        """
        Gerekli tabloları oluşturur ve eski veritabanlarını
        veri kaybetmeden güncel şemaya geçirir.
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            # 1. İzlenen yollar
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitored_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 2. Güvenilir dosya parmak izleri
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

            # 3. İzleme oturumları
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

            # 4. Her oturumda seçilen dosya ve klasörler
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

            # 5. Güvenlik olayları
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

            # Eski security_events tablosunda session_id olmayabilir.
            # Bu kontrol mevcut kayıtları silmeden sütunu ekler.
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

            # Oturuma göre olay sorgularını hızlandırır.
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_security_events_session_id
                ON security_events(session_id)
            """)

            connection.commit()

    def add_monitored_path(self, path: str) -> int:
        """İzlenecek bir yolu kaydeder ve kayıt ID'sini döndürür."""
        absolute_path = os.path.abspath(path)
        created_at = datetime.now().isoformat(timespec="milliseconds")

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO monitored_paths (
                    path,
                    created_at
                )
                VALUES (?, ?)
            """, (absolute_path, created_at))

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

    def get_baseline_for_path(self, path_id: int) -> Dict[str, str]:
        """Kayıtlı baseline hash değerlerini dosya yoluna göre döndürür."""
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
        """
        Güvenlik olayını kaydeder ve oluşturulan olay ID'sini döndürür.

        session_id şimdilik isteğe bağlıdır. Böylece mevcut watcher kodu
        değişmeden çalışmaya devam eder.
        """
        timestamp = datetime.now().isoformat(timespec="milliseconds")

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

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """En son güvenlik olaylarını yeni kayıttan eskiye doğru döndürür."""
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT *
                FROM security_events
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))

            return [
                dict(row)
                for row in cursor.fetchall()
            ]