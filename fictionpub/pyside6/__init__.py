"""
PySide6 GUI entry point for fictionpub.
Drop-in replacement for the Tkinter gui.py module:

    from fictionpub.pyside6 import run_gui
    run_gui()
"""

import logging
import sys

from PySide6.QtWidgets import QApplication

from ..utils.logger import setup_main_logger
from .i18n import set_language
from .main_window import MainWindow
from .state.settings import AppSettings
from .themes import apply_theme


def run_gui() -> None:
    setup_main_logger(logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("fb2converter")
    app.setOrganizationName("fictionpub")
    # Fusion renders identically on all platforms and supports custom palettes.
    app.setStyle("Fusion")

    settings = AppSettings()
    set_language(settings.language())
    apply_theme(app, settings.theme())

    window = MainWindow(settings)

    geometry = settings.geometry()
    if geometry:
        window.restoreGeometry(geometry)
    else:
        window.resize(1100, 650)

    window.show()
    sys.exit(app.exec())