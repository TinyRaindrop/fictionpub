"""
Background thread that recursively collects .fb2 / .fb2.zip files
from a list of input paths (files or directories).
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    filesFound = Signal(list)   # list[Path]

    def __init__(self, input_paths: list[Path], parent=None):
        super().__init__(parent)
        self._paths = input_paths

    def run(self) -> None:
        found: list[Path] = []
        for p in self._paths:
            if p.is_file():
                name = p.name
                if name.endswith(".fb2") or name.endswith(".fb2.zip"):
                    found.append(p)
            elif p.is_dir():
                for pattern in ("**/*.fb2", "**/*.fb2.zip"):
                    found.extend(p.rglob(pattern))
        self.filesFound.emit(found)
