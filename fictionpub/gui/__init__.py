"""
GUI entry point for fictionpub.

    from fictionpub.gui import run_gui
    run_gui()

Language bootstrap order
------------------------
1. If the user has previously saved a language preference it is loaded from
   QSettings and used as-is.
2. On the very first launch (no saved pref.) the OS locale is inspected via QLocale.system().
   If it resolves to a supported language ('en' / 'uk') that language is pre-selected.
   Otherwise 'en' is the fallback.
"""

import logging
import sys

from PySide6.QtCore import QLocale
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import app_info
from ..resources.loader import get_icon_path
from ..utils.logger import setup_main_logger
from .i18n import set_language
from .main_window import MainWindow
from .state.settings import AppSettings
from .themes import apply_theme

_SUPPORTED_LANGS = {"en", "uk"}
_SETTINGS_LANG_KEY_SENTINEL = "__unset__"  # value stored when no preference exists yet


def _detect_os_language() -> str:
    """
    Return the best supported language code based on the OS locale.
    Uses Qt's QLocale so it is consistent with Qt's own locale handling
    across all platforms (Windows, macOS, Linux).

    QLocale.system().name() returns "uk_UA", "en_GB", "de_DE".
    We take the first two characters as the ISO 639-1 code.
    """
    locale_name = QLocale.system().name()
    code = locale_name[:2].lower() if locale_name else "en"
    return code if code in _SUPPORTED_LANGS else "en"


def run_gui() -> None:
    # TODO: ensure loggin setup is consistent between CLI and GUI
    setup_main_logger(logging.INFO)

    # Write a session marker for log folder viewer.
    log = logging.getLogger("fb2_converter")
    log.info("APP_START mode=gui")

    app = QApplication(sys.argv)
    app.setApplicationName(app_info.APP_NAME)
    app.setOrganizationName(app_info.APP_NAME_SHORT)
    # Fusion renders identically on all platforms and works with custom palettes.
    app.setStyle("Fusion")

    # App icon — set on the QApplication so every window (including dialogs)
    # inherits it automatically.  QIcon handles .ico on all platforms.
    icon_path = get_icon_path("app.ico")
    if icon_path and icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = AppSettings()

    # --- Language resolution ---
    # AppSettings.language() returns "en" as the default when nothing is saved.
    # We distinguish "explicitly saved as en" from "never set" by checking
    # whether the key exists in QSettings at all.
    raw_lang = settings._s.value("app/language", _SETTINGS_LANG_KEY_SENTINEL)
    if raw_lang == _SETTINGS_LANG_KEY_SENTINEL:
        # First launch — detect from OS and persist so it's not re-detected
        # on every subsequent run.
        lang = _detect_os_language()
        settings.set_language(lang)
    else:
        lang = str(raw_lang)
        if lang not in _SUPPORTED_LANGS:
            lang = "en"

    set_language(lang)

    # --- Theme ---
    apply_theme(app, settings.theme())

    # --- Main window ---
    window = MainWindow(settings)

    geometry = settings.get_geometry()
    if geometry:
        window.restoreGeometry(geometry)
    else:
        window.resize(1280, 720)

    window.show()
    sys.exit(app.exec())
