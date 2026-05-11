"""
Pool-based worker for parsing file metadata.
QRunnable cannot emit signals directly, so a companion QObject
(MetaSignals) is created alongside each task and connected before
submission to QThreadPool.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from fictionpub.core.fb2_book import FB2Book


class MetaSignals(QObject):
    """Signals companion for MetaWorker."""

    meta_parsed = Signal(object, object)  # (Path, QuickMetadata)
    meta_failed = Signal(object, str)  # (Path, error_msg)


class MetaWorker(QRunnable):
    def __init__(self, path: Path, signals: MetaSignals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            meta = FB2Book.get_quick_metadata(self.path)
            self.signals.meta_parsed.emit(self.path, meta)
        except Exception as e:
            self.signals.meta_failed.emit(self.path, str(e))
