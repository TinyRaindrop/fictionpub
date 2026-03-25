"""
Data node classes for the file tree model.
eq=False ensures identity-based comparison, which is required for
safe use as QModelIndex internal pointers and in sets/dicts.
"""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt

from ...models.conversion import ConversionStatus


@dataclass(eq=False)
class FileNode:
    path: Path
    check_state: Qt.CheckState = Qt.CheckState.Checked
    status: ConversionStatus | None = None
    log_output: str = ""
    error: str | None = None
    metadata: object | None = None   # QuickMetadata, typed loosely to avoid circular import
    meta_loading: bool = False


@dataclass(eq=False)
class FolderNode:
    path: Path
    check_state: Qt.CheckState = Qt.CheckState.Checked
    children: list[FileNode] = field(default_factory=list)
