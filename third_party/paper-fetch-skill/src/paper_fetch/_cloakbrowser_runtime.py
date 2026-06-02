"""Process-local CloakBrowser integration helpers."""

from __future__ import annotations

import threading
from typing import Any


_SUPPRESS_LOCK = threading.Lock()
_WELCOME_SUPPRESSED = False


def suppress_cloakbrowser_welcome(cloakbrowser: Any) -> None:
    """Disable CloakBrowser's first-launch promotional stderr banner."""
    global _WELCOME_SUPPRESSED
    with _SUPPRESS_LOCK:
        if _WELCOME_SUPPRESSED:
            return
        try:
            from cloakbrowser import download as cloakbrowser_download
        except Exception:
            cloakbrowser_download = getattr(cloakbrowser, "download", None)
        if cloakbrowser_download is not None:
            try:
                cloakbrowser_download._show_welcome = lambda: None
            except Exception:
                pass
        _WELCOME_SUPPRESSED = True


def import_cloakbrowser() -> Any:
    import cloakbrowser

    suppress_cloakbrowser_welcome(cloakbrowser)
    return cloakbrowser


__all__ = [
    "import_cloakbrowser",
    "suppress_cloakbrowser_welcome",
]
