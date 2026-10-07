import os
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
    EVENT_TYPES = {
        "MODIFIED",
        "CREATED",
        "DELETED",
        "RESTORED",
        "MOVED",
        "PERMISSIONS_CHANGED",
        "OWNERSHIP_CHANGED",
        "SYMLINK_CHANGED",
        "POSSIBLE_COPY",
        "CLIPBOARD_COPY",
        "CONTENT_CLIPBOARD_COPY",
    }

    RISK_LEVELS = {
        "LOW",
        "MEDIUM",
        "HIGH",
    }

    @staticmethod
    def _normalize_last_modified_ns(value) -> int:
        """
        Eski saniye biçimini ve yeni nanosaniye biçimini
        ortak nanosaniye değerine dönüştürür.
        """
        try:
            numeric_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(
                f"Geçersiz dosya zamanı: {value!r}"
            ) from error

        # Eski YULA zamanları Unix saniyesi olarak saklıyordu.
        # Yeni YULA st_mtime_ns ile nanosaniye saklıyor.
        if numeric_value < Decimal("10000000000"):
            numeric_value *= Decimal("1000000000")

        return int(numeric_value)

    def __init__(self, db_path: str = "yula.db"):
        self.db_path = os.path.abspath(
            os.path.expanduser(db_path)
        )
        self._prepare_database_file()
        self._init_db()

    def _prepare_database_file(self) -> None:
        """
        Veritabanını güvenli bir normal dosya olarak hazırlar.

        Unix sistemlerinde yalnızca dosyanın sahibine
        okuma ve yazma yetkisi verir.
        """
        parent_directory = os.path.dirname(
            self.db_path
        )

        os.makedirs(
            parent_directory,
            mode=0o700,
            exist_ok=True,
        )

        if os.path.lexists(self.db_path):
            if os.path.islink(self.db_path):
                raise ValueError(
                    "Veritabanı yolu sembolik bağlantı olamaz."
                )

            if not os.path.isfile(self.db_path):
                raise ValueError(
                    "Veritabanı yolu normal bir dosya olmalıdır."
                )

        else:
            open_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
            )

            if hasattr(os, "O_NOFOLLOW"):
                open_flags |= os.O_NOFOLLOW

            file_descriptor = os.open(
                self.db_path,
                open_flags,
                0o600,
            )
            os.close(file_descriptor)

        if os.name != "nt":
            os.chmod(
                self.db_path,
                0o600,
            )

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
                    file_mode INTEGER,
                    owner_uid INTEGER,
                    group_gid INTEGER,
                    file_kind TEXT,
                    symlink_target TEXT,

                    FOREIGN KEY (path_id)
                        REFERENCES monitored_paths(id)
                        ON DELETE CASCADE,

                    UNIQUE(path_id, file_path)
                )
            """)

            baseline_columns = {
                row["name"]
                for row in cursor.execute(
                    "PRAGMA table_info(file_baselines)"
                ).fetchall()
            }
            baseline_column_definitions = {
                "file_mode": "INTEGER",
                "owner_uid": "INTEGER",
                "group_gid": "INTEGER",
                "file_kind": "TEXT",
                "symlink_target": "TEXT",
            }
            for column_name, column_type in baseline_column_definitions.items():
                if column_name not in baseline_columns:
                    cursor.execute(
                        f"ALTER TABLE file_baselines "
                        f"ADD COLUMN {column_name} {column_type}"
                    )

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

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_control (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    desired_state TEXT NOT NULL CHECK (
                        desired_state IN ('RUNNING', 'STOPPED')
                    ),
                    session_id INTEGER,
                    process_id INTEGER,
                    heartbeat_at TEXT,
                    updated_at TEXT NOT NULL,

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

            event_column_definitions = {
                "source_path": "TEXT",
                "details_json": "TEXT",
                "actor_name": "TEXT",
                "actor_source": "TEXT",
            }

            for column_name, column_type in event_column_definitions.items():
                if column_name not in event_columns:
                    cursor.execute(
                        f"ALTER TABLE security_events "
                        f"ADD COLUMN {column_name} {column_type}"
                    )

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_security_events_session_id
                ON security_events(session_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_security_events_timestamp
                ON security_events(timestamp)
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

    def list_monitoring_sessions(
        self,
        limit: int = 100,
    ) -> List[Dict]:
        """Son izleme çalışmalarını hedefleri ve olay sayılarıyla döndürür."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Çalışma limiti pozitif bir tam sayı olmalıdır.")

        with self._get_connection() as connection:
            rows = connection.execute("""
                SELECT
                    monitoring_sessions.*,
                    COUNT(security_events.id) AS event_count
                FROM monitoring_sessions
                LEFT JOIN security_events
                    ON security_events.session_id = monitoring_sessions.id
                GROUP BY monitoring_sessions.id
                ORDER BY monitoring_sessions.id DESC
                LIMIT ?
            """, (limit,)).fetchall()

            sessions = []
            for row in rows:
                session = dict(row)
                target_rows = connection.execute("""
                    SELECT target_path, target_type
                    FROM session_targets
                    WHERE session_id = ?
                    ORDER BY id
                """, (session["id"],)).fetchall()
                session["targets"] = [dict(target) for target in target_rows]
                sessions.append(session)

            return sessions

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
                        last_modified,
                        file_mode,
                        owner_uid,
                        group_gid,
                        file_kind,
                        symlink_target
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                    ON CONFLICT(path_id, file_path)
                    DO UPDATE SET
                        sha256_hash = excluded.sha256_hash,
                        file_size = excluded.file_size,
                        last_modified = excluded.last_modified,
                        file_mode = excluded.file_mode,
                        owner_uid = excluded.owner_uid,
                        group_gid = excluded.group_gid,
                        file_kind = excluded.file_kind,
                        symlink_target = excluded.symlink_target
                """, (
                    path_id,
                    file_path,
                    data["hash"],
                    data["size"],
                    str(data["last_modified"]),
                    data.get("mode"),
                    data.get("uid"),
                    data.get("gid"),
                    data.get("kind"),
                    data.get("symlink_target"),
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

    def get_baseline_snapshots_for_targets(
        self,
        targets: list[str],
    ) -> Dict[str, dict]:
        """Arka plan ajanının devam edebilmesi için kayıtlı görüntüleri döndürür."""
        if not targets:
            return {}

        normalized_targets = [
            os.path.abspath(os.path.expanduser(target))
            for target in targets
        ]
        placeholders = ", ".join("?" for _ in normalized_targets)

        with self._get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    file_path,
                    sha256_hash,
                    file_size,
                    last_modified,
                    file_mode,
                    owner_uid,
                    group_gid,
                    file_kind,
                    symlink_target
                FROM file_baselines
                INNER JOIN monitored_paths
                    ON monitored_paths.id = file_baselines.path_id
                WHERE monitored_paths.path IN ({placeholders})
                """,
                normalized_targets,
            ).fetchall()

        snapshots = {}
        for row in rows:
            snapshot = {
                "hash": row["sha256_hash"],
                "size": row["file_size"],
                "last_modified": self._normalize_last_modified_ns(
                    row["last_modified"]
                ),
            }
            optional_values = {
                "mode": row["file_mode"],
                "uid": row["owner_uid"],
                "gid": row["group_gid"],
                "kind": row["file_kind"],
                "symlink_target": row["symlink_target"],
            }
            snapshot.update({
                key: value
                for key, value in optional_values.items()
                if value is not None
            })
            snapshot["is_symlink"] = snapshot.get("kind") == "SYMLINK"
            snapshots[row["file_path"]] = snapshot

        return snapshots

    def request_agent_start(self, session_id: int) -> None:
        """Arka plan ajanı için kalıcı çalışma isteği oluşturur."""
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._get_connection() as connection:
            connection.execute("""
                INSERT INTO agent_control (
                    id,
                    desired_state,
                    session_id,
                    process_id,
                    heartbeat_at,
                    updated_at
                )
                VALUES (1, 'RUNNING', ?, NULL, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    desired_state = 'RUNNING',
                    session_id = excluded.session_id,
                    process_id = NULL,
                    heartbeat_at = NULL,
                    updated_at = excluded.updated_at
            """, (session_id, now))

    def request_agent_stop(self) -> None:
        """Ajanın güvenli biçimde durması için kalıcı istek bırakır."""
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._get_connection() as connection:
            connection.execute("""
                UPDATE agent_control
                SET desired_state = 'STOPPED', updated_at = ?
                WHERE id = 1
            """, (now,))

    def update_agent_heartbeat(self, process_id: int) -> None:
        """Ajanın canlılık bilgisini günceller."""
        now = datetime.now().isoformat(timespec="milliseconds")
        with self._get_connection() as connection:
            connection.execute("""
                UPDATE agent_control
                SET process_id = ?, heartbeat_at = ?, updated_at = ?
                WHERE id = 1
            """, (process_id, now, now))

    def get_agent_state(self) -> Dict | None:
        """Kalıcı ajan isteğini ve canlılık bilgisini döndürür."""
        with self._get_connection() as connection:
            row = connection.execute("""
                SELECT *
                FROM agent_control
                WHERE id = 1
            """).fetchone()
            return dict(row) if row else None

    def log_security_event(
        self,
        event_type: str,
        risk_level: str,
        target_path: str,
        description: str,
        session_id: int | None = None,
        source_path: str | None = None,
        details: dict | None = None,
        actor_name: str | None = None,
        actor_source: str | None = None,
    ) -> int:
        """Doğrulanmış güvenlik olayını veritabanına kaydeder."""
        if not isinstance(event_type, str):
            raise ValueError(
                "Olay türü metin olmalıdır."
            )

        normalized_event_type = (
            event_type.strip().upper()
        )

        if normalized_event_type not in self.EVENT_TYPES:
            raise ValueError(
                f"Geçersiz olay türü: {event_type}"
            )

        if not isinstance(risk_level, str):
            raise ValueError(
                "Risk seviyesi metin olmalıdır."
            )

        normalized_risk_level = (
            risk_level.strip().upper()
        )

        if normalized_risk_level not in self.RISK_LEVELS:
            raise ValueError(
                f"Geçersiz risk seviyesi: {risk_level}"
            )

        if (
            not isinstance(target_path, str)
            or not target_path.strip()
        ):
            raise ValueError(
                "Güvenlik olayının geçerli bir hedef yolu "
                "olmalıdır."
            )

        normalized_target_path = os.path.abspath(
            os.path.expanduser(
                target_path.strip()
            )
        )

        if (
            not isinstance(description, str)
            or not description.strip()
        ):
            raise ValueError(
                "Güvenlik olayının açıklaması boş olamaz."
            )

        normalized_description = description.strip()

        normalized_source_path = None
        if source_path is not None:
            if not isinstance(source_path, str) or not source_path.strip():
                raise ValueError(
                    "Kaynak yolu metin olmalı ve boş olmamalıdır."
                )
            normalized_source_path = os.path.abspath(
                os.path.expanduser(source_path.strip())
            )

        if details is not None and not isinstance(details, dict):
            raise ValueError("Olay ayrıntıları sözlük olmalıdır.")

        details_json = (
            json.dumps(
                details,
                ensure_ascii=False,
                sort_keys=True,
            )
            if details is not None
            else None
        )

        for field_name, field_value in (
            ("Aktör adı", actor_name),
            ("Aktör kaynağı", actor_source),
        ):
            if field_value is not None and (
                not isinstance(field_value, str)
                or not field_value.strip()
            ):
                raise ValueError(f"{field_name} boş bir metin olamaz.")

        normalized_actor_name = actor_name.strip() if actor_name else None
        normalized_actor_source = actor_source.strip() if actor_source else None

        if (
            session_id is not None
            and (
                isinstance(session_id, bool)
                or not isinstance(session_id, int)
                or session_id < 1
            )
        ):
            raise ValueError(
                "İzleme çalışması kimliği pozitif "
                "bir tam sayı olmalıdır."
            )

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
                    session_id,
                    source_path,
                    details_json,
                    actor_name,
                    actor_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                normalized_event_type,
                normalized_risk_level,
                normalized_target_path,
                normalized_description,
                session_id,
                normalized_source_path,
                details_json,
                normalized_actor_name,
                normalized_actor_source,
            ))

            event_id = cursor.lastrowid

            if event_id is None:
                raise RuntimeError(
                    "Güvenlik olayı kaydedilemedi."
                )

            return event_id

    def get_events_in_range(
        self,
        start_at: datetime,
        end_at: datetime,
        session_id: int | None = None,
    ) -> List[Dict]:
        """Verilen tarih-saat aralığındaki olayları kronolojik döndürür."""
        if not isinstance(start_at, datetime) or not isinstance(end_at, datetime):
            raise ValueError("Rapor başlangıç ve bitişi tarih-saat olmalıdır.")
        if start_at > end_at:
            raise ValueError("Rapor başlangıcı bitişinden sonra olamaz.")

        parameters: list[object] = [
            start_at.isoformat(timespec="milliseconds"),
            end_at.isoformat(timespec="milliseconds"),
        ]
        session_filter = ""
        if session_id is not None:
            session_filter = "AND session_id = ?"
            parameters.append(session_id)

        with self._get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM security_events
                WHERE timestamp BETWEEN ? AND ?
                {session_filter}
                ORDER BY timestamp, id
                """,
                parameters,
            ).fetchall()

            events = []
            for row in rows:
                event = dict(row)
                event["details"] = (
                    json.loads(event["details_json"])
                    if event.get("details_json")
                    else None
                )
                events.append(event)

            return events

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

    def get_event_groups(
        self,
        session_id: int,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Aynı izleme çalışmasındaki olayları hedef yoluna göre gruplar.

        Her grup için son olay, toplam olay sayısı,
        ilk-son görülme zamanı ve en yüksek riski döndürür.
        """
        if limit < 1:
            raise ValueError(
                "Grup limiti en az 1 olmalıdır."
            )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                WITH ranked_events AS (
                    SELECT
                        id,
                        timestamp,
                        event_type,
                        risk_level,
                        target_path,
                        description,
                        session_id,
                        source_path,
                        actor_name,
                        actor_source,

                        ROW_NUMBER() OVER (
                            PARTITION BY target_path
                            ORDER BY id DESC
                        ) AS row_number,

                        COUNT(*) OVER (
                            PARTITION BY target_path
                        ) AS event_count,

                        MIN(timestamp) OVER (
                            PARTITION BY target_path
                        ) AS first_seen,

                        MAX(timestamp) OVER (
                            PARTITION BY target_path
                        ) AS last_seen,

                        MAX(
                            CASE risk_level
                                WHEN 'HIGH' THEN 3
                                WHEN 'MEDIUM' THEN 2
                                ELSE 1
                            END
                        ) OVER (
                            PARTITION BY target_path
                        ) AS highest_risk_score

                    FROM security_events
                    WHERE session_id = ?
                )

                SELECT
                    id,
                    timestamp,
                    event_type,
                    risk_level AS latest_risk,

                    CASE highest_risk_score
                        WHEN 3 THEN 'HIGH'
                        WHEN 2 THEN 'MEDIUM'
                        ELSE 'LOW'
                    END AS highest_risk,

                    target_path,
                    description,
                    session_id,
                    source_path,
                    actor_name,
                    actor_source,
                    event_count,
                    first_seen,
                    last_seen

                FROM ranked_events
                WHERE row_number = 1
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

    def get_events_for_target(
        self,
        session_id: int,
        target_path: str,
        limit: int = 200,
    ) -> List[Dict]:
        """Bir hedefe ait ayrıntılı olay geçmişini döndürür."""
        if limit < 1:
            raise ValueError(
                "Olay limiti en az 1 olmalıdır."
            )

        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT *
                FROM security_events
                WHERE
                    session_id = ?
                    AND target_path = ?
                ORDER BY id DESC
                LIMIT ?
            """, (
                session_id,
                target_path,
                limit,
            ))

            return [
                dict(row)
                for row in cursor.fetchall()
            ]
