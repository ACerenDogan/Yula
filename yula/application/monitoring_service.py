import logging
import os
from collections.abc import Callable, Iterable

from yula.core.paths import (
    normalize_path,
    should_ignore_path,
)
from yula.core.scanner import scan_targets
from yula.core.watcher import YulaWatcher
from yula.storage.database import DatabaseManager


logger = logging.getLogger(__name__)


class MonitoringService:
    """
    Bir izleme çalışmasının bütün yaşam döngüsünü yönetir.

    Sorumlulukları:

    1. Hedefleri doğrulamak
    2. İzleme çalışmasını veritabanında oluşturmak
    3. Baseline taraması yapmak
    4. Baseline kayıtlarını saklamak
    5. Watcher'ı başlatmak
    6. Çalışma durumunu güncellemek
    7. Watcher'ı güvenli şekilde durdurmak
    """

    def __init__(
        self,
        database: DatabaseManager,
        event_callback: Callable[[dict], None] | None = None,
        scanner: Callable[[Iterable[str]], dict] = scan_targets,
        watcher_factory: Callable[..., YulaWatcher] = YulaWatcher,
    ):
        self.database = database
        self.event_callback = event_callback
        self.scanner = scanner
        self.watcher_factory = watcher_factory

        self._watcher: YulaWatcher | None = None
        self._session_id: int | None = None
        self._targets: tuple[str, ...] = ()

    @property
    def session_id(self) -> int | None:
        """Aktif izleme çalışmasının ID değerini döndürür."""
        return self._session_id

    @property
    def targets(self) -> tuple[str, ...]:
        """Aktif çalışmada izlenen hedefleri döndürür."""
        return self._targets

    @property
    def is_running(self) -> bool:
        """Watcher'ın gerçekten çalışıp çalışmadığını döndürür."""
        return (
            self._watcher is not None
            and self._watcher.is_running
        )

    def _prepare_targets(
        self,
        targets: Iterable[str],
    ) -> list[dict]:
        """
        Kullanıcıdan gelen yolları doğrular ve normalize eder.

        DatabaseManager'ın beklediği şu yapıyı oluşturur:

        [
            {"path": "/project/app.py", "type": "FILE"},
            {"path": "/project/config", "type": "DIRECTORY"},
        ]
        """
        prepared_targets = []
        seen_paths = set()

        for target in targets:
            normalized = normalize_path(target)

            if normalized in seen_paths:
                continue

            if not os.path.lexists(normalized):
                raise FileNotFoundError(
                    f"İzleme hedefi bulunamadı: {normalized}"
                )

            if should_ignore_path(normalized):
                raise ValueError(
                    f"Bu hedef Yula tarafından izlenemez: "
                    f"{normalized}"
                )

            target_type = (
                "DIRECTORY"
                if os.path.isdir(normalized)
                and not os.path.islink(normalized)
                else "FILE"
            )

            prepared_targets.append({
                "path": normalized,
                "type": target_type,
            })

            seen_paths.add(normalized)

        if not prepared_targets:
            raise ValueError(
                "İzlemek için en az bir dosya veya klasör "
                "seçilmelidir."
            )

        return prepared_targets

    def start(
        self,
        targets: Iterable[str],
    ) -> int:
        """
        Yeni izleme çalışmasını başlatır.

        Başarılı olursa izleme çalışmasının ID değerini döndürür.
        """
        if self._session_id is not None:
            raise RuntimeError(
                "Zaten aktif bir izleme çalışması var."
            )

        prepared_targets = self._prepare_targets(targets)

        session_id = (
            self.database.create_monitoring_session(
                prepared_targets
            )
        )

        watcher = None

        try:
            combined_baseline = {}
            target_baselines = {}

            for target in prepared_targets:
                target_path = target["path"]

                scan_result = self.scanner([
                    target_path
                ])

                target_baselines[target_path] = scan_result
                combined_baseline.update(scan_result)

            for target in prepared_targets:
                target_path = target["path"]

                path_id = (
                    self.database.add_monitored_path(
                        target_path
                    )
                )

                self.database.save_baseline_records(
                    path_id,
                    target_baselines[target_path],
                )

            normalized_targets = tuple(
                target["path"]
                for target in prepared_targets
            )

            watcher = self.watcher_factory(
                targets=normalized_targets,
                baseline_data=combined_baseline,
                db=self.database,
                event_callback=self.event_callback,
                session_id=session_id,
            )

            watcher.start()

            self.database.set_monitoring_session_status(
                session_id,
                "RUNNING",
            )

            self._watcher = watcher
            self._session_id = session_id
            self._targets = normalized_targets

            return session_id

        except Exception:
            if watcher is not None:
                try:
                    watcher.stop()
                except Exception:
                    logger.exception(
                        "Başlatma hatası watcher "
                        "durdurulurken hata oluştu."
                    )

            try:
                self.database.set_monitoring_session_status(
                    session_id,
                    "ERROR",
                )
            except Exception:
                logger.exception(
                    "Hatalı izleme çalışmasının durumu "
                    "güncellenemedi."
                )

            raise
 
    def stop(self) -> None:
        """Aktif izleme çalışmasını güvenli şekilde durdurur"""
        if self._watcher is None or self._session_id is None:
            return

        watcher = self._watcher
        session_id = self._session_id

        try:
            watcher.stop()

            self.database.set_monitoring_session_status(
                session_id,
                "STOPPED",
            )

        except Exception:
            try:
                self.database.set_monitoring_session_status(
                    session_id,
                    "ERROR",
                )
            except Exception:
                logger.exception(
                    "İzleme çalışması ERROR durumuna "
                    "alınamadı."
                )

            raise

        finally:
            self._watcher = None
            self._session_id = None
            self._targets = ()
