import os
import plistlib
import sys
from pathlib import Path


LAUNCH_AGENT_LABEL = "com.yula.file-integrity-agent"


def install_launch_agent(
    database_path: str,
    project_root: str | None = None,
    python_executable: str | None = None,
    launch_agents_directory: str | None = None,
    log_directory: str | None = None,
) -> str:
    """YULA ajanının kullanıcı girişinde yeniden başlaması için plist oluşturur."""
    root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
    python_path = os.path.abspath(python_executable or sys.executable)
    database_path = os.path.abspath(database_path)
    launch_directory = Path(
        launch_agents_directory
        or os.path.expanduser("~/Library/LaunchAgents")
    )
    log_directory_path = Path(
        log_directory
        or os.path.expanduser("~/Library/Logs/YULA")
    )
    launch_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    log_directory_path.mkdir(mode=0o700, parents=True, exist_ok=True)

    plist_path = launch_directory / f"{LAUNCH_AGENT_LABEL}.plist"
    temporary_path = launch_directory / f".{LAUNCH_AGENT_LABEL}.plist.tmp"
    configuration = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            python_path,
            "-m",
            "yula.application.agent_worker",
            "--db",
            database_path,
            "--resume",
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Background",
        "StandardOutPath": str(log_directory_path / "agent.log"),
        "StandardErrorPath": str(log_directory_path / "agent-error.log"),
    }

    with open(temporary_path, "wb") as plist_file:
        plistlib.dump(configuration, plist_file, sort_keys=True)
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, plist_path)
    return str(plist_path)
