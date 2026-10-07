import argparse
import signal

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from yula.core.clipboard_monitor import ClipboardFileMonitor
from yula.storage.database import DatabaseManager


def run_clipboard_worker(database_path: str, session_id: int) -> int:
    """macOS panosunu izler; ana dosya ajanından bağımsız çalışır."""
    database = DatabaseManager(database_path)
    session = database.get_monitoring_session(session_id)
    if session is None:
        return 1

    targets = [target["target_path"] for target in session["targets"]]
    application = QGuiApplication.instance() or QGuiApplication(
        ["YULA Pano İzleyicisi"]
    )
    application.setQuitOnLastWindowClosed(False)
    monitor = ClipboardFileMonitor(
        clipboard=application.clipboard(),
        database=database,
        targets=targets,
        session_id=session_id,
    )
    monitor.poll()

    stop_requested = False

    def request_stop(_signal_number=None, _frame=None):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def process_tick():
        state = database.get_agent_state()
        if (
            stop_requested
            or state is None
            or state["desired_state"] != "RUNNING"
            or state["session_id"] != session_id
        ):
            application.quit()
            return
        monitor.poll()

    timer = QTimer()
    timer.timeout.connect(process_tick)
    timer.start(500)
    return application.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="YULA pano izleme yardımcısı")
    parser.add_argument("--db", required=True, help="YULA SQLite veritabanı")
    parser.add_argument("--session-id", required=True, type=int)
    arguments = parser.parse_args()
    return run_clipboard_worker(arguments.db, arguments.session_id)


if __name__ == "__main__":
    raise SystemExit(main())
