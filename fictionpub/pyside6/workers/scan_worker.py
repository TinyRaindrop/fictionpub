"""
Background thread that recursively collects .fb2 / .fb2.zip files
from a list of input paths (files or directories).

Each discovered file is emitted as a (scan_root, file_path) tuple:
  - For an individual file:  scan_root = file.parent
  - For a directory:         scan_root = the directory itself

The scan_root is used by FileTreeModel.addFiles() to anchor the visible
tree hierarchy: files are nested beneath their scan_root, with all
intermediate subdirectories created automatically.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    # list[tuple[Path, Path]]  — (scan_root, file_path)
    filesFound = Signal(list)

    def __init__(self, input_paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self._paths = input_paths

    def run(self) -> None:
        found: list[tuple[Path, Path]] = []
        for p in self._paths:
            if p.is_file():
                name = p.name
                if name.endswith(".fb2") or name.endswith(".fb2.zip"):
                    found.append((p.parent, p))
            elif p.is_dir():
                for pattern in ("**/*.fb2", "**/*.fb2.zip"):
                    for f in p.rglob(pattern):
                        found.append((p, f))
        self.filesFound.emit(found)