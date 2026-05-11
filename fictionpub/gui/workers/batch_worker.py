"""
QThread that wraps BatchProcessor.run().

Progress is forwarded to the main thread via Qt signals (QueuedConnection
is the default for cross-thread connections, so this is thread-safe).

IMPORTANT: The signal is named `batchFinished` (not `finished`) to avoid
shadowing QThread's built-in `finished()` signal which Qt emits internally
when the thread ends. A name collision causes unpredictable signal delivery.

Cancellation: sets a flag that stops progress signal emission. The
ProcessPoolExecutor inside BatchProcessor continues to its natural end —
we do not forcibly kill child processes. Any remaining results are discarded.
Since BatchWorker is re-created for each run, the cancel flag is always
fresh on the next conversion.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from fictionpub.core.batch_processor import BatchProcessor
from fictionpub.models.conversion import ConversionConfig, ConversionResult


class BatchWorker(QThread):
    progress_update = Signal(object)  # ConversionResult
    batch_finished = Signal(object)  # ConversionSession
    error_occurred = Signal(str)

    def __init__(
        self,
        config: ConversionConfig,
        files: list[Path],
        session,  # ConversionSession — typed loosely to avoid circular import
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._files = files
        self._session = session
        self._cancel_requested = False  # always False on a fresh instance

    def request_cancel(self) -> None:
        """
        Signal that the user wants to stop. Safe to call from the main thread.
        The flag is checked inside _callback (runs on this thread).
        """
        self._cancel_requested = True

    def run(self) -> None:
        try:
            processor = BatchProcessor(self._config)
            processor.run(self._files, self._callback)
        except Exception as e:
            if not self._cancel_requested:
                self.error_occurred.emit(str(e))
        finally:
            self._session.cancelled = self._cancel_requested
            self.batch_finished.emit(self._session)

    def _callback(self, result: ConversionResult) -> None:
        """Called by BatchProcessor for each completed file (on this thread)."""
        if self._cancel_requested:
            return
        self._session.update(result)
        self.progress_update.emit(result)
