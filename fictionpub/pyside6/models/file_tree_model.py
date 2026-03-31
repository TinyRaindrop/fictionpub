"""
Arbitrary-depth tree model: FolderNode → (FolderNode | FileNode)*

Column layout
─────────────
COL_NAME   0  filename + checkbox
COL_STATUS 1  status icon; UserRole returns int sort key
COL_AUTHOR 2
COL_TITLE  3
COL_DATE   4
COL_LANG   5

Root-level FolderNodes display their full path.
Nested FolderNodes display only their name (the nesting implies the path).

addFiles()
──────────
Accepts list[tuple[Path, Path]] where each tuple is (scan_root, file_path).
scan_root anchors the visible tree top for that file; intermediate folders
between scan_root and file_path.parent are created automatically.
If a path already exists in the model (folder or file) it is reused, so
adding a sub-folder of an already-visible folder merges cleanly.

Check-state propagation
───────────────────────
• Checking/unchecking a folder cascades to all descendants.
• Changing a file bubbles up through all ancestor folders, which are
  recalculated to Checked / Unchecked / PartiallyChecked.

Collapse/expand
───────────────
QTreeView handles collapse/expand natively through the expand-arrow on
every FolderNode.  The model does not force any expansion state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap

from ...models.conversion import ConversionStatus
from ..i18n import t
from .file_node import FileNode, FolderNode

IndexType = Union[QModelIndex, QPersistentModelIndex]

# ── Column constants ──────────────────────────────────────────────────────────
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
_STATUS_SORT_KEY: dict[ConversionStatus | None, int] = {
    None:                     0,
    ConversionStatus.FAILURE: 1,
    ConversionStatus.WARNING: 2,
    ConversionStatus.SUCCESS: 3,
}

_ICON_SIZE = 16


def _load_png_icon(filename: str, size: int = _ICON_SIZE) -> QIcon | None:
    # TODO: move to loader_gui
    try:
        from ...resources.loader_gui import get_icon_path
        path = get_icon_path(filename)
        if path and path.is_file():
            px = QPixmap(str(path))
            if not px.isNull():
                return QIcon(px.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
    except Exception:
        pass
    return None


def _make_fallback_icon(symbol: str, color: str, size: int = _ICON_SIZE) -> QIcon:
    """Glyph icon used when the PNG resource is unavailable."""
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


# ─────────────────────────────────────────────────────────────────────────────

class FileTreeModel(QAbstractItemModel):
    """
    Hierarchical file-tree model supporting arbitrary folder nesting.
    Root entries are FolderNodes; they may contain more FolderNodes and/or
    FileNodes at any depth.
    """

    # (checked_count, total_count)
    selectionCountChanged = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root_folders: list[FolderNode] = []
        self._path_to_node: dict[Path, FileNode]   = {}
        self._folder_map:   dict[Path, FolderNode] = {}

        self._status_icons: dict[ConversionStatus, QIcon] = {
            ConversionStatus.SUCCESS: (
                _load_png_icon("status_success.png") or _make_fallback_icon("✓", "#27ae60")
            ),
            ConversionStatus.WARNING: (
                _load_png_icon("status_warning.png") or _make_fallback_icon("⚠", "#e67e22")
            ),
            ConversionStatus.FAILURE: (
                _load_png_icon("status_failure.png")   or _make_fallback_icon("✗", "#e74c3c")
            ),
        }

    # ── QAbstractItemModel interface ──────────────────────────────────────────

    def index(self, row: int, column: int, parent: IndexType = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            if row < len(self._root_folders):
                return self.createIndex(row, column, self._root_folders[row])
        else:
            ptr = parent.internalPointer()
            if isinstance(ptr, FolderNode) and row < len(ptr.children):
                return self.createIndex(row, column, ptr.children[row])
        return QModelIndex()

    def parent(self, index: IndexType) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent_node: FolderNode | None = node.parent
        if parent_node is None:
            return QModelIndex()
        # Find parent_node's row within its own parent
        grandparent = parent_node.parent
        if grandparent is None:
            row = self._root_folders.index(parent_node)
        else:
            row = grandparent.children.index(parent_node)
        return self.createIndex(row, 0, parent_node)

    def rowCount(self, parent: IndexType = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._root_folders)
        ptr = parent.internalPointer()
        return len(ptr.children) if isinstance(ptr, FolderNode) else 0

    def columnCount(self, parent: IndexType = QModelIndex()) -> int:
        return COLUMNS

    def flags(self, index: IndexType) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_NAME:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(_HEADER_KEYS):
                return t(_HEADER_KEYS[section])
        return None

    def data(self, index: IndexType, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        col  = index.column()
        if isinstance(node, FolderNode):
            return self._folder_data(node, col, role)
        if isinstance(node, FileNode):
            return self._file_data(node, col, role)
        return None

    def setData(self, index: IndexType, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        node  = index.internalPointer()
        state = Qt.CheckState(value)

        if isinstance(node, FolderNode):
            node.check_state = state
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            if state != Qt.CheckState.PartiallyChecked:
                self._cascade_check(node, state, index)
            # Bubble up to parent folders
            parent_idx = self.parent(index)
            if parent_idx.isValid():
                self._recalc_ancestors(parent_idx.internalPointer(), parent_idx)

        elif isinstance(node, FileNode):
            node.check_state = state
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            parent_idx = self.parent(index)
            if parent_idx.isValid():
                self._recalc_ancestors(parent_idx.internalPointer(), parent_idx)

        self._emit_selection_count()
        return True

    # ── Public mutation API ───────────────────────────────────────────────────

    def addFiles(self, items: list[tuple[Path, Path]]) -> int:
        """
        Add files to the model.

        Parameters
        ----------
        items : list of (scan_root, file_path)
            scan_root becomes the top-level tree entry for its group of files.
            Intermediate folders between scan_root and file_path.parent are
            created automatically and nested accordingly.

        Returns the number of new files added (duplicates are skipped).
        """
        added = 0
        for scan_root, file_path in items:
            if file_path in self._path_to_node:
                continue

            folder = self._ensure_folder_chain(file_path.parent, scan_root)
            folder_idx = self._index_for_node(folder)
            row = len(folder.children)
            self.beginInsertRows(folder_idx, row, row)
            node = FileNode(path=file_path, parent=folder, meta_loading=True)
            folder.children.append(node)
            self._path_to_node[file_path] = node
            self.endInsertRows()
            added += 1

        if added:
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
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.ToolTipRole])
            status_idx = self.createIndex(idx.row(), COL_STATUS, node)
            self.dataChanged.emit(
                status_idx, status_idx,
                [Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.UserRole],
            )

    def removeNodes(self, indices: list[QModelIndex]) -> None:
        """Remove selected nodes (folders recursively, files individually)."""
        # Collect unique node objects
        nodes: set = {idx.internalPointer() for idx in indices if idx.isValid()}

        # Keep only "root" nodes of the selection (skip if an ancestor is also selected)
        def _has_ancestor_in(node, node_set: set) -> bool:
            p = node.parent
            while p is not None:
                if p in node_set:
                    return True
                p = p.parent
            return False

        roots = [n for n in nodes if not _has_ancestor_in(n, nodes)]

        # Group removal roots by their parent
        by_parent: dict = {}
        for node in roots:
            by_parent.setdefault(node.parent, []).append(node)

        for parent, node_list in by_parent.items():
            if parent is None:
                # Root-level folders
                rows = sorted(
                    [self._root_folders.index(n) for n in node_list], reverse=True
                )
                for row in rows:
                    self.beginRemoveRows(QModelIndex(), row, row)
                    removed = self._root_folders.pop(row)
                    self._deregister_subtree(removed)
                    self.endRemoveRows()
            else:
                parent_idx = self._index_for_node(parent)
                rows = sorted(
                    [parent.children.index(n) for n in node_list], reverse=True
                )
                for row in rows:
                    self.beginRemoveRows(parent_idx, row, row)
                    removed = parent.children.pop(row)
                    if isinstance(removed, FileNode):
                        self._path_to_node.pop(removed.path, None)
                    else:
                        self._deregister_subtree(removed)
                    self.endRemoveRows()
                self._prune_empty_ancestors(parent)

        self._emit_selection_count()

    def removeAll(self) -> None:
        if not self._root_folders:
            return
        self.beginResetModel()
        self._root_folders.clear()
        self._path_to_node.clear()
        self._folder_map.clear()
        self.endResetModel()
        self._emit_selection_count()

    def removeCompleted(self) -> None:
        """Remove all SUCCESS files; prune folders that become empty."""
        # Group success files by immediate parent
        by_parent: dict[FolderNode, list[FileNode]] = {}
        for node in self._path_to_node.values():
            if node.status == ConversionStatus.SUCCESS:
                by_parent.setdefault(node.parent, []).append(node)

        if not by_parent:
            return

        for parent, nodes in by_parent.items():
            parent_idx = self._index_for_node(parent)
            rows = sorted(
                [parent.children.index(n) for n in nodes], reverse=True
            )
            for row in rows:
                self.beginRemoveRows(parent_idx, row, row)
                removed = parent.children.pop(row)
                self._path_to_node.pop(removed.path, None)
                self.endRemoveRows()

        # Prune empty folders (deepest first to avoid double-pruning)
        candidates = sorted(
            [p for p in by_parent if not p.children],
            key=lambda f: len(f.path.parts),
            reverse=True,
        )
        seen: set[int] = set()
        for folder in candidates:
            if id(folder) not in seen:
                self._prune_empty_ancestors(folder)
                seen.add(id(folder))

        self._emit_selection_count()

    def setAllChecked(self, is_checked: bool) -> None:
        state = Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked
        for i, folder in enumerate(self._root_folders):
            folder.check_state = state
            root_idx = self.index(i, 0)
            self.dataChanged.emit(root_idx, root_idx, [Qt.ItemDataRole.CheckStateRole])
            self._cascade_check(folder, state, root_idx)
        self._emit_selection_count()

    def checkedFilePaths(self) -> list[Path]:
        return [
            node.path
            for node in self._path_to_node.values()
            if node.check_state == Qt.CheckState.Checked
        ]

    def nodeForIndex(self, index: QModelIndex) -> FileNode | FolderNode | None:
        return index.internalPointer() if index.isValid() else None

    def totalFileCount(self) -> int:
        return len(self._path_to_node)

    # ── Private: folder-chain creation ───────────────────────────────────────

    def _ensure_folder_chain(self, folder_path: Path, scan_root: Path) -> FolderNode:
        """
        Return the FolderNode for folder_path, creating it and all intermediate
        folders between scan_root and folder_path if they do not yet exist.
        scan_root is always the topmost entry for this chain.
        """
        # Reuse an existing node (may already be nested inside another scan root)
        if folder_path in self._folder_map:
            return self._folder_map[folder_path]

        # Anchor: scan_root (or filesystem root) becomes a root-level entry
        if folder_path == scan_root or folder_path.parent == folder_path:
            folder = FolderNode(path=folder_path, parent=None)
            row = len(self._root_folders)
            self.beginInsertRows(QModelIndex(), row, row)
            self._root_folders.append(folder)
            self._folder_map[folder_path] = folder
            self.endInsertRows()
            return folder

        # Create parent first, then create this folder as a child
        parent_folder = self._ensure_folder_chain(folder_path.parent, scan_root)
        folder = FolderNode(path=folder_path, parent=parent_folder)
        parent_idx = self._index_for_node(parent_folder)
        row = len(parent_folder.children)
        self.beginInsertRows(parent_idx, row, row)
        parent_folder.children.append(folder)
        self._folder_map[folder_path] = folder
        self.endInsertRows()
        return folder

    # ── Private: check-state helpers ─────────────────────────────────────────

    def _cascade_check(
        self,
        folder: FolderNode,
        state: Qt.CheckState,
        folder_idx: QModelIndex,
    ) -> None:
        """Set state on all immediate children, then recurse into sub-folders."""
        if not folder.children:
            return
        for child in folder.children:
            child.check_state = state
        first = self.index(0, 0, folder_idx)
        last  = self.index(len(folder.children) - 1, 0, folder_idx)
        self.dataChanged.emit(first, last, [Qt.ItemDataRole.CheckStateRole])
        for i, child in enumerate(folder.children):
            if isinstance(child, FolderNode):
                self._cascade_check(child, state, self.index(i, 0, folder_idx))

    def _recalc_ancestors(self, folder: FolderNode, folder_idx: QModelIndex) -> None:
        """Recalculate tri-state for folder and all ancestor folders."""
        all_files = list(self._iter_files(folder))
        if not all_files:
            return
        states = {f.check_state for f in all_files}
        new_state = states.pop() if len(states) == 1 else Qt.CheckState.PartiallyChecked
        if folder.check_state != new_state:
            folder.check_state = new_state
            self.dataChanged.emit(folder_idx, folder_idx, [Qt.ItemDataRole.CheckStateRole])
        parent_idx = self.parent(folder_idx)
        if parent_idx.isValid():
            self._recalc_ancestors(parent_idx.internalPointer(), parent_idx)

    # ── Private: removal helpers ──────────────────────────────────────────────

    def _deregister_subtree(self, folder: FolderNode) -> None:
        """Remove folder and all its contents from the lookup maps."""
        self._folder_map.pop(folder.path, None)
        for child in folder.children:
            if isinstance(child, FileNode):
                self._path_to_node.pop(child.path, None)
            else:
                self._deregister_subtree(child)

    def _prune_empty_ancestors(self, folder: FolderNode) -> None:
        """Remove folder if empty; then recurse up if its parent also becomes empty."""
        # Guard: only operate on nodes still registered in the model
        if self._folder_map.get(folder.path) is not folder:
            return
        if folder.children:
            return

        parent = folder.parent
        if parent is None:
            row = self._root_folders.index(folder)
            self.beginRemoveRows(QModelIndex(), row, row)
            self._root_folders.pop(row)
            self._folder_map.pop(folder.path, None)
            self.endRemoveRows()
        else:
            parent_idx = self._index_for_node(parent)
            row = parent.children.index(folder)
            self.beginRemoveRows(parent_idx, row, row)
            parent.children.pop(row)
            self._folder_map.pop(folder.path, None)
            self.endRemoveRows()
            self._prune_empty_ancestors(parent)

    # ── Private: generic helpers ──────────────────────────────────────────────

    def _iter_files(self, folder: FolderNode):
        """Yield every FileNode in folder's subtree (recursive)."""
        for child in folder.children:
            if isinstance(child, FileNode):
                yield child
            else:
                yield from self._iter_files(child)

    def _index_for_node(self, node: FileNode | FolderNode) -> QModelIndex:
        """Return the col-0 QModelIndex for any node in the tree."""
        parent = node.parent
        try:
            if parent is None:
                row = self._root_folders.index(node)
            else:
                row = parent.children.index(node)
        except ValueError:
            return QModelIndex()
        return self.createIndex(row, 0, node)

    def _emit_selection_count(self) -> None:
        total   = len(self._path_to_node)
        checked = sum(
            1 for n in self._path_to_node.values()
            if n.check_state == Qt.CheckState.Checked
        )
        self.selectionCountChanged.emit(checked, total)

    # ── Private: data helpers ─────────────────────────────────────────────────

    def _folder_data(self, node: FolderNode, col: int, role: int):
        if col == COL_NAME:
            if role == Qt.ItemDataRole.DisplayRole:
                # Root folders → full path; nested → name only
                return str(node.path) if node.parent is None else node.path.name
            if role == Qt.ItemDataRole.CheckStateRole:
                return node.check_state.value
            if role == Qt.ItemDataRole.FontRole:
                f = QFont()
                f.setBold(True)
                return f
        return None

    def _file_data(self, node: FileNode, col: int, role: int):
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

        elif col == COL_STATUS:
            if role == Qt.ItemDataRole.DecorationRole:
                return self._status_icons.get(node.status)
            if role == Qt.ItemDataRole.UserRole:
                return _STATUS_SORT_KEY.get(node.status, 0)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter

        elif role == Qt.ItemDataRole.DisplayRole:
            meta = node.metadata
            if meta is None:
                return "…" if node.meta_loading else ""
            if col == COL_AUTHOR: return getattr(meta, "author", "") or ""
            if col == COL_TITLE:  return getattr(meta, "title",  "") or ""
            if col == COL_DATE:   return getattr(meta, "date",   "") or ""
            if col == COL_LANG:   return getattr(meta, "lang",   "") or ""

        return None