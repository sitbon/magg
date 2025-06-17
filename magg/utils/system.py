import os
import shutil
from pathlib import Path
from typing import Optional

try:
    from rich import console, pretty, traceback

    _rc: console.Console | None = None

except (ImportError, ModuleNotFoundError):
    pass

__all__ = "chown", "initterm"


def chown(path: Path, uid: int | str | None = None, gid: int | str | None = None, *, recursive: bool = False) -> None:
    if os.getuid() != 0:
        return

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    gid = gid if gid is not None else uid
    shutil.chown(path, uid, gid if gid is not None else uid)

    if recursive and path.is_dir():
        for root, dirs, files in path.walk():
            for d in dirs:
                shutil.chown(root / d, uid, gid if gid is not None else uid)
            for f in files:
                shutil.chown(root / f, uid, gid if gid is not None else uid)


def initterm(**kwds) -> Optional["console.Console"]:
    try:
        if not os.isatty(0):
            return None

    except (AttributeError, OSError):
        return None

    try:
        global _rc

        if _rc is not None:
            return _rc

        kwds.setdefault("color_system", "truecolor")
        _rc = console.Console(**kwds)
        pretty.install(console=_rc)
        traceback.install(console=_rc, show_locals=True)
        return _rc

    except NameError:
        return None
