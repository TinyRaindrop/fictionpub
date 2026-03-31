"""
Data node classes for the file tree model.

eq=False ensures identity-based comparison, which is required for safe
use as QModelIndex internal pointers and in sets / dicts.

parent back-reference
---------------------
Both FolderNode and FileNode carry a reference to their parent FolderNode
(None for root-level folders).  This makes QAbstractItemModel.parent()
O(1) and eliminates the need to search the tree when navigating upward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Union

from PySide6.QtCore import Qt

from ...models.conversion import ConversionStatus

if TYPE_CHECKING:
    pass   # avoid circular import; typing only


@dataclass(eq=False)
class FileNode:
    path:         Path
    parent:       "FolderNode"                     # always set; never None
    check_state:  Qt.CheckState = Qt.CheckState.Checked
    status:       ConversionStatus | None = None
    log_output:   str = ""
    error:        str | None = None
    metadata:     object | None = None             # QuickMetadata (loosely typed)
    meta_loading: bool = False


@dataclass(eq=False)
class FolderNode:
    path:        Path
    parent:      "FolderNode | None"               # None for root entries
    check_state: Qt.CheckState = Qt.CheckState.Checked
    children:    list[Union["FolderNode", FileNode]] = field(default_factory=list)