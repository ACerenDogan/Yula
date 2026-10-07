import getpass
import os
import sys


def get_context_user() -> tuple[str | None, str]:
    """
    Olay anındaki oturum hesabını döndürür.

    Bu bilgi işlemi yapan kişiyi kanıtlamaz; yalnızca olay gözlenirken
    etkin olan kullanıcı bağlamını belirtir.
    """
    if sys.platform == "darwin":
        try:
            import pwd

            console_uid = os.stat("/dev/console").st_uid
            return pwd.getpwuid(console_uid).pw_name, "CONSOLE_CONTEXT"
        except (KeyError, OSError):
            pass

    try:
        return getpass.getuser(), "PROCESS_CONTEXT"
    except (KeyError, OSError):
        return None, "UNAVAILABLE"
