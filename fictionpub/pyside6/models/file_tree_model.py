"""
Two-level tree model: FolderNode (top) → FileNode (children).

Column layout
-------------
COL_NAME   0  filename + checkbox (no status icon here)
COL_STATUS 1  status icon only; UserRole returns an int sort key
COL_AUTHOR 2
COL_TITLE  3
COL_DATE   4
COL_LANG   5

Status sort keys (ascending = worst first):
  None (not converted) → 0
  FAILURE              → 1
  WARNING              → 2
  SUCCESS              → 3

Internal pointer strategy:
  FolderNode indices:  createIndex(row, col, folder_node)
  FileNode indices:    createIndex(row, col, file_node)

Icons are created in __init__() — NOT at module import time —
to avoid the "Must construct a QGuiApplication before a QPixmap" error.
"""

from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap

from ...models.conversion import ConversionStatus
from ..i18n import t
from .file_node import FileNode, FolderNode

# Column indices — plain ints, no Qt objects at import time
COL_NAME   = 0
COL_STATUS = 1
COL_AUTHOR = 2
COL_TITLE  = 3
COL_DATE   = 4
COL_LANG   = 5
COLUMNS    = 6

_HEADER_KEYS = [
    "tree.col_name",
    "tree.col_status",
    "tree.col_author",
    "tree.col_title",
    "tree.col_date",
    "tree.col_lang",
]

# Sort priority: lower = shown first in ascending sort.
# Failures are most important to see first.
_STATUS_SORT_KEY: dict[ConversionStatus | None, int] = {
    None:                    0,
    ConversionStatus.FAILURE: 1,
    ConversionStatus.WARNING: 2,
    ConversionStatus.SUCCESS: 3,
}


def _make_icon(symbol: str, color: str, size: int = 14) -> QIcon:
    """Build a small icon from a Unicode symbol. QApplication must already exist."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(color))
    font = p.font()
    font.setPixelSize(size - 1)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, symbol)
    p.end()
    return QIcon(px)


class FileTreeModel(QAbstractItemModel):
    """
    Hierarchical model: folders at the root, files as their children.
    Files start checked; folder tri-state is derived from children.
    """

    # Emitted whenever any CheckState changes.
    # Args: (checked_file_count, total_file_count)
    selectionCountChanged = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folders: list[FolderNode] = []
        self._path_to_node: dict[Path, FileNode] = {}

        # Icons created here — QGuiApplication exists at this point
        self._status_icons: dict[ConversionStatus, QIcon] = {
            ConversionStatus.SUCCESS: _make_icon("✓", "#27ae60"),
            ConversionStatus.WARNING: _make_icon("⚠", "#e67e22"),
            ConversionStatus.FAILURE: _make_icon("✗", "#e74c3c"),
        }

    # ------------------------------------------------------------------
    # QAbstractItemModel interface
    # ------------------------------------------------------------------

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            if row < len(self._folders):
                return self.createIndex(row, column, self._folders[row])
        else:
            ptr = parent.internalPointer()
            if isinstance(ptr, FolderNode) and row < len(ptr.children):
                return self.createIndex(row, column, ptr.children[row])
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if isinstance(node, FolderNode):
            return QModelIndex()
        if isinstance(node, FileNode):
            for i, folder in enumerate(self._folders):
                if any(child is node for child in folder.children):
                    return self.createIndex(i, 0, folder)
        return QModelIndex()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._folders)
        ptr = parent.internalPointer()
        if isinstance(ptr, FolderNode):
            return len(ptr.children)
        return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return COLUMNS

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_NAME:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(_HEADER_KEYS):
                return t(_HEADER_KEYS[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        col  = index.column()
        if isinstance(node, FolderNode):
            return self._folder_data(node, col, role)
        if isinstance(node, FileNode):
            return self._file_data(node, col, role)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        node  = index.internalPointer()
        state = Qt.CheckState(value)

        if isinstance(node, FolderNode):
            node.check_state = state
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            if state != Qt.CheckState.PartiallyChecked and node.children:
                for child in node.children:
                    child.check_state = state
                first = self.index(0, 0, index)
                last  = self.index(len(node.children) - 1, 0, index)
                self.dataChanged.emit(first, last, [Qt.ItemDataRole.CheckStateRole])

        elif isinstance(node, FileNode):
            node.check_state = state
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            parent_idx = self.parent(index)
            if parent_idx.isValid():
                folder = parent_idx.internalPointer()
                self._recalc_folder_state(folder, parent_idx)

        self._emit_selection_count()
        return True

    # ------------------------------------------------------------------
    # Public mutation API
    # ------------------------------------------------------------------

    def addFiles(self, paths: list[Path]) -> int:
        """Add new file paths grouped by parent directory. Returns count added."""
        existing      = set(self._path_to_node.keys())
        folder_lookup = {f.path: f for f in self._folders}

        new_by_folder: dict[Path, list[Path]] = {}
        for p in paths:
            if p not in existing:
                new_by_folder.setdefault(p.parent, []).append(p)

        if not new_by_folder:
            return 0

        added = 0
        for folder_path, file_paths in new_by_folder.items():
            if folder_path not in folder_lookup:
                row = len(self._folders)
                self.beginInsertRows(QModelIndex(), row, row)
                folder = FolderNode(path=folder_path)
                self._folders.append(folder)
                folder_lookup[folder_path] = folder
                self.endInsertRows()

            folder     = folder_lookup[folder_path]
            folder_row = self._folders.index(folder)
            folder_idx = self.createIndex(folder_row, 0, folder)

            start = len(folder.children)
            end   = start + len(file_paths) - 1
            self.beginInsertRows(folder_idx, start, end)
            for p in file_paths:
                node = FileNode(path=p, meta_loading=True)
                folder.children.append(node)
                self._path_to_node[p] = node
            self.endInsertRows()
            added += len(file_paths)

        self._emit_selection_count()
        return added

    def updateMeta(self, path: Path, meta) -> None:
        node = self._path_to_node.get(path)
        if not node:
            return
        node.metadata     = meta
        node.meta_loading = False
        idx = self._index_for_node(node)
        if idx.isValid():
            left  = self.createIndex(idx.row(), COL_AUTHOR, node)
            right = self.createIndex(idx.row(), COL_LANG,   node)
            self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole])

    def updateMetaError(self, path: Path, _error: str) -> None:
        node = self._path_to_node.get(path)
        if not node:
            return
        node.meta_loading = False
        node.metadata     = None
        idx = self._index_for_node(node)
        if idx.isValid():
            left  = self.createIndex(idx.row(), COL_AUTHOR, node)
            right = self.createIndex(idx.row(), COL_LANG,   node)
            self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole])

    def setFileResult(self, path: Path, result) -> None:
        node = self._path_to_node.get(path)
        if not node:
            return
        node.status     = result.status
        node.log_output = result.log_output
        node.error      = str(result.error) if result.error else None
        idx = self._index_for_node(node)
        if idx.isValid():
            # Status column carries both the icon (DecorationRole) and sort key (UserRole)
            status_idx = self.createIndex(idx.row(), COL_STATUS, node)
            self.dataChanged.emit(
                idx, idx, [Qt.ItemDataRole.ToolTipRole]
            )
            self.dataChanged.emit(
                status_idx, status_idx,
                [Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.UserRole],
            )

    def removeNodes(self, indices: list[QModelIndex]) -> None:
        folders_to_delete: set[FolderNode] = set()
        files_by_folder:   dict[FolderNode, set[FileNode]] = {}

        for idx in indices:
            if not idx.isValid():
                continue
            node = idx.internalPointer()
            if isinstance(node, FolderNode):
                folders_to_delete.add(node)
            elif isinstance(node, FileNode):
                parent_idx = self.parent(idx)
                folder     = parent_idx.internalPointer() if parent_idx.isValid() else None
                if isinstance(folder, FolderNode) and folder not in folders_to_delete:
                    files_by_folder.setdefault(folder, set()).add(node)

        for folder, files in files_by_folder.items():
            folder_row   = self._folders.index(folder)
            folder_index = self.createIndex(folder_row, 0, folder)
            rows = sorted(
                [i for i, c in enumerate(folder.children) if c in files],
                reverse=True,
            )
            for row in rows:
                self.beginRemoveRows(folder_index, row, row)
                removed = folder.children.pop(row)
                self._path_to_node.pop(removed.path, None)
                self.endRemoveRows()
            if not folder.children:
                folders_to_delete.add(folder)

        folder_rows = sorted(
            [i for i, f in enumerate(self._folders) if f in folders_to_delete],
            reverse=True,
        )
        for row in folder_rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            removed_folder = self._folders.pop(row)
            for child in removed_folder.children:
                self._path_to_node.pop(child.path, None)
            self.endRemoveRows()

        self._emit_selection_count()

    def removeAll(self) -> None:
        if not self._folders:
            return
        self.beginResetModel()
        self._folders.clear()
        self._path_to_node.clear()
        self.endResetModel()
        self._emit_selection_count()

    def removeCompleted(self) -> None:
        for folder in list(self._folders):
            if folder not in self._folders:
                continue
            folder_row   = self._folders.index(folder)
            folder_index = self.createIndex(folder_row, 0, folder)
            rows = sorted(
                [i for i, c in enumerate(folder.children)
                 if c.status == ConversionStatus.SUCCESS],
                reverse=True,
            )
            for row in rows:
                self.beginRemoveRows(folder_index, row, row)
                removed = folder.children.pop(row)
                self._path_to_node.pop(removed.path, None)
                self.endRemoveRows()

        empty_rows = sorted(
            [i for i, f in enumerate(self._folders) if not f.children],
            reverse=True,
        )
        for row in empty_rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            self._folders.pop(row)
            self.endRemoveRows()

        self._emit_selection_count()

    def setAllChecked(self, state: Qt.CheckState) -> None:
        for folder in self._folders:
            folder.check_state = state
            for child in folder.children:
                child.check_state = state

        if self._folders:
            top_left  = self.index(0, 0)
            top_right = self.index(len(self._folders) - 1, 0)
            self.dataChanged.emit(top_left, top_right, [Qt.ItemDataRole.CheckStateRole])
            for i, folder in enumerate(self._folders):
                if folder.children:
                    parent_idx = self.index(i, 0)
                    first = self.index(0, 0, parent_idx)
                    last  = self.index(len(folder.children) - 1, 0, parent_idx)
                    self.dataChanged.emit(first, last, [Qt.ItemDataRole.CheckStateRole])

        self._emit_selection_count()

    def checkedFilePaths(self) -> list[Path]:
        return [
            node.path
            for folder in self._folders
            for node in folder.children
            if node.check_state == Qt.CheckState.Checked
        ]

    def nodeForIndex(self, index: QModelIndex) -> "FileNode | FolderNode | None":
        if not index.isValid():
            return None
        return index.internalPointer()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _folder_data(self, node: FolderNode, col: int, role: int):
        if col == COL_NAME:
            if role == Qt.ItemDataRole.DisplayRole:
                return str(node.path)
            if role == Qt.ItemDataRole.CheckStateRole:
                return node.check_state.value
            if role == Qt.ItemDataRole.FontRole:
                f = QFont()
                f.setBold(True)
                return f
        return None

    def _file_data(self, node: FileNode, col: int, role: int):
        # --- Name column ---
        if col == COL_NAME:
            if role == Qt.ItemDataRole.DisplayRole:
                return node.path.name
            if role == Qt.ItemDataRole.CheckStateRole:
                return node.check_state.value
            if role == Qt.ItemDataRole.ToolTipRole:
                if node.status == ConversionStatus.FAILURE and node.error:
                    return node.error
                if node.status == ConversionStatus.WARNING:
                    return t("tooltip.warning_status")
            if role == Qt.ItemDataRole.ForegroundRole:
                if node.check_state == Qt.CheckState.Unchecked:
                    return QBrush(QColor("#888888"))

        # --- Status column ---
        elif col == COL_STATUS:
            if role == Qt.ItemDataRole.DecorationRole:
                return self._status_icons.get(node.status)
            if role == Qt.ItemDataRole.UserRole:
                # Integer sort key used by QSortFilterProxyModel
                return _STATUS_SORT_KEY.get(node.status, 0)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter

        # --- Metadata columns ---
        elif role == Qt.ItemDataRole.DisplayRole:
            meta = node.metadata
            if meta is None:
                return "…" if node.meta_loading else ""
            if col == COL_AUTHOR: return getattr(meta, "author", "") or ""
            if col == COL_TITLE:  return getattr(meta, "title",  "") or ""
            if col == COL_DATE:   return getattr(meta, "date",   "") or ""
            if col == COL_LANG:   return getattr(meta, "lang",   "") or ""

        return None

    def _recalc_folder_state(self, folder: FolderNode, folder_index: QModelIndex) -> None:
        if not folder.children:
            return
        states = {child.check_state for child in folder.children}
        if len(states) == 1:
            folder.check_state = states.pop()
        else:
            folder.check_state = Qt.CheckState.PartiallyChecked
        self.dataChanged.emit(folder_index, folder_index, [Qt.ItemDataRole.CheckStateRole])

    def _index_for_node(self, node: FileNode) -> QModelIndex:
        for folder in self._folders:
            for j, child in enumerate(folder.children):
                if child is node:
                    return self.createIndex(j, 0, node)
        return QModelIndex()

    def _emit_selection_count(self) -> None:
        total   = sum(len(f.children) for f in self._folders)
        checked = sum(
            1 for f in self._folders
            for c in f.children
            if c.check_state == Qt.CheckState.Checked
        )
        self.selectionCountChanged.emit(checked, total)