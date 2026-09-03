import sqlite3
import os
from datetime import datetime
from typing import Dict, List


class DatabaseManager:
    """
    Yula yerel SQLite veritabanı yönetim sınıfı.
    İzlenen dizinleri, baseline parmak izlerini ve güvenlik loglarını saklar.
    """
    def __init__(self, db_path: str = "yula.db"):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Veritabanı bağlantısı açar ve satırları sözlük gibi okumamızı sağlar."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        """Uygulama tablolarını oluşturur."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. İzlenen Dizinler Tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitored_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 2. Dosya Parmak İzi (Baseline) Tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    last_modified TEXT NOT NULL,
                    FOREIGN KEY (path_id) REFERENCES monitored_paths(id) ON DELETE CASCADE,
                    UNIQUE(path_id, file_path)
                )
            """)

            # 3. Güvenlik Olayları Tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    target_path TEXT,
                    description TEXT NOT NULL
                )
            """)
            conn.commit()

    def add_monitored_path(self, path: str) -> int:
        """İzlenecek yeni bir klasör kaydeder ve ID'sini döner."""
        abs_path = os.path.abspath(path)
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO monitored_paths (path, created_at)
                VALUES (?, ?)
            """, (abs_path, now))
            conn.commit()

            cursor.execute("SELECT id FROM monitored_paths WHERE path = ?", (abs_path,))
            row = cursor.fetchone()
            return row["id"] if row else -1

    def save_baseline_records(self, path_id: int, scan_results: Dict[str, dict]):
        """
        scanner.py tarafından bulunan tüm dosyaların parmak izlerini
        veritabanına 'Güvenilir Baseline' olarak kilitler.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for filepath, data in scan_results.items():
                cursor.execute("""
                    INSERT INTO file_baselines (path_id, file_path, sha256_hash, file_size, last_modified)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(path_id, file_path) DO UPDATE SET
                        sha256_hash = excluded.sha256_hash,
                        file_size = excluded.file_size,
                        last_modified = excluded.last_modified
                """, (path_id, filepath, data["hash"], data["size"], str(data["last_modified"])))
            conn.commit()
            print(f"💾 {len(scan_results)} adet dosyanın parmak izi veritabanına (Baseline) kilitlendi.")

    def get_baseline_for_path(self, path_id: int) -> Dict[str, str]:
        """Veritabanındaki kayıtlı baseline hash haritasını {dosya_yolu: hash} döner."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path, sha256_hash FROM file_baselines WHERE path_id = ?", (path_id,))
            return {row["file_path"]: row["sha256_hash"] for row in cursor.fetchall()}

    def log_security_event(self, event_type: str, risk_level: str, target_path: str, description: str) -> int:
        """Oluşan güvenlik olayını kalıcı olarak SQLite'a kaydeder."""
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO security_events (timestamp, event_type, risk_level, target_path, description)
                VALUES (?, ?, ?, ?, ?)
            """, (now, event_type, risk_level, target_path, description))
            conn.commit()
            return cursor.lastrowid

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        """Veritabanındaki en son güvenlik olaylarını döner."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]    
