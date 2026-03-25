"""
QThread that wraps BatchProcessor.run().

Progress is forwarded to the main thread via Qt signals (QueuedConnection
is the default for cross-thread connections, so this is thread-safe).

Cancellation is "soft": we stop emitting UI signals but cannot immediately
halt the ProcessPoolExecutor without modifying BatchProcessor. The worker
thread finishes naturally but silently after cancel is requested.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ...core.batch_processor import BatchProcessor
from ...models.conversion import ConversionConfig, ConversionResult


class BatchWorker(QThread):
    progressUpdate = Signal(object)   # ConversionResult
    finished       = Signal(object)   # ConversionSession (dataclass from main_window)
    errorOccurred  = Signal(str)

    def __init__(
        self,
        config: ConversionConfig,
        files: list[Path],
        session,            # ConversionSession — typed loosely to avoid circular import
        parent=None,
    ):
        super().__init__(parent)
        self._config  = config
        self._files   = files
        self._session = session
        self._cancel_requested = False

    def requestCancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            processor = BatchProcessor(self._config)
            processor.run(self._files, self._callback)
        except Exception as e:
            if not self._cancel_requested:
                self.errorOccurred.emit(str(e))
        finally:
            self._session.cancelled = self._cancel_requested
            self.finished.emit(self._session)

    def _callback(self, result: ConversionResult) -> None:
        if self._cancel_requested:
            return
        self._session.update(result)
        self.progressUpdate.emit(result)
