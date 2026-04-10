"""
FileTreeView — QTreeView configured for the file list.

Column layout
  0  Filename  + checkbox              (auto-fills remaining width)
  1  Status    icon                    (fixed, non-resizable)
  2  Author
  3  Title
  4  Date
  5  Lang

NaturalSortProxyModel
─────────────────────
Replaces the plain QSortFilterProxyModel to give:
  • FolderNodes always appear before FileNodes at the same tree level.
  • Status column sorted by integer key (UserRole) so failures sort first.
  • All other columns sorted by natural_collation_key():
      - digit runs sorted numerically (21 before 200)
      - Ukrainian ґ ordered after г, not after я

Initial default sort is Col.NAME ascending so the sort indicator is on
the Name column and there is no ambiguity about the arrow on Col.STATUS.
Col.STATUS is set to Fixed resize mode so the narrow icon column cannot
be inadvertently dragged wider.

Click behaviour
───────────────
Single click  Col.STATUS → open log viewer
Double click  FileNode   → open EPUB (SUCCESS/WARNING) or log (FAILURE)
Double click  FolderNode → open directory in file manager

Selective expand
────────────────
expandNewFolders(nodes) expands only freshly added root FolderNodes;
existing expand state is preserved.

Drag-drop
─────────
Files and folders can be dropped directly onto the view.
The view accepts drops of local file URLs (hasUrls + isLocalFile),
emits filesDropped(list[Path]), and lets MainWindow call _start_scan()
exactly as if the user had clicked "Add Files" / "Add Folder".

Only external drops are accepted (DragDropMode.DropOnly).
Internal row-reordering drags are intentionally not supported.
"""  # noqa: RUF002

from pathlib import Path
from typing import override

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeView

from ..models.conversion import ConversionStatus
from .i18n import register_listener, t
from .models.collation import natural_collation_key
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import Col, FileTreeModel

_COL_NAME_MIN = 120  # px — filename col is never auto-shrunk below this
_COL_STATUS_W = 36  # px — fixed status column width


# ─────────────────────────────────────────────────────────────────────────────


class NaturalSortProxyModel(QSortFilterProxyModel):
    """
    Proxy model with natural + Cyrillic collation sort order.

    lessThan() is fully manual so setSortRole() is irrelevant here; we
    leave the role at the default DisplayRole but never call the base
    implementation's data fetch.
    """

    @override
    def lessThan(
        self,
        left: QModelIndex | QPersistentModelIndex,
        right: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        model = self.sourceModel()
        col = left.column()

        left_node = model.node_for_index(left)
        right_node = model.node_for_index(right)

        # ── Folders always sort before files at the same level ────────────
        left_folder = isinstance(left_node, FolderNode)
        right_folder = isinstance(right_node, FolderNode)
        if left_folder != right_folder:
            return left_folder  # folder < file  →  True when left is folder

        # ── Status column: integer sort key stored in UserRole ────────────
        if col == Col.STATUS:
            lv = model.data(left, Qt.ItemDataRole.UserRole) or 0
            rv = model.data(right, Qt.ItemDataRole.UserRole) or 0
            return int(lv) < int(rv)

        # ── All other columns: natural + Cyrillic collation ──────────────
        ld = model.data(left, Qt.ItemDataRole.DisplayRole) or ""
        rd = model.data(right, Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(ld, str) and isinstance(rd, str):
            return natural_collation_key(ld) < natural_collation_key(rd)

        return super().lessThan(left, right)


# ─────────────────────────────────────────────────────────────────────────────


class FileTreeView(QTreeView):
    status_clicked = Signal(object)  # FileNode
    folder_double_clicked = Signal(object)  # Path
    open_epub_requested = Signal(object)  # Path
    open_fb2_requested = Signal(object)  # Path
    open_folder_requested = Signal(object)  # Path
    selection_remove_requested = Signal()
    files_dropped = Signal(list)  # list[Path] — files and/or folders

    def __init__(self, model: FileTreeModel, parent=None):
        super().__init__(parent)
        self._source_model = model

        self._proxy = NaturalSortProxyModel(self)
        self._proxy.setSourceModel(model)
        self._proxy.setDynamicSortFilter(True)
        # TODO: add drag&drop support
        self.setModel(self._proxy)
        self.setSortingEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Accept drops of local files/folders from the OS file manager.
        # DropOnly so no internal row-reordering drags are ever started.
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDropIndicatorShown(False)  # no insertion-point caret needed

        self._setup_header()

        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)

        register_listener(self._on_language_changed)

    # ------------------------------------------------------------------
    # Header / column setup
    # ------------------------------------------------------------------

    def _setup_header(self) -> None:
        h = self.header()
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(24)

        # Default: all columns interactive
        for col in Col:
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Status column: fixed width, not user-resizable
        h.setSectionResizeMode(Col.STATUS, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(Col.STATUS, _COL_STATUS_W)

        # Initial widths for the other columns
        h.resizeSection(Col.NAME, 320)
        h.resizeSection(2, 160)  # Author
        h.resizeSection(3, 200)  # Title
        h.resizeSection(4, 70)  # Date
        h.resizeSection(5, 50)  # Lang

        # Sort by Name ascending on startup.
        self.sortByColumn(Col.NAME, Qt.SortOrder.AscendingOrder)

    # ------------------------------------------------------------------
    # Window resize: Col.NAME auto-fills remaining viewport width
    # ------------------------------------------------------------------

    @override
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fill_name_column()

    def _fill_name_column(self) -> None:
        h = self.header()
        vp_width = self.viewport().width()
        # Sum all columns except Col.NAME (which absorbs the remaining space)
        other_sum = sum(h.sectionSize(c) for c in Col if c != Col.NAME)
        new_w = max(_COL_NAME_MIN, vp_width - other_sum)

        # blockSignals prevents the programmatic resize from being treated as
        # a user drag and from triggering any connected sectionResized slots.
        h.blockSignals(True)
        h.resizeSection(Col.NAME, new_w)
        h.blockSignals(False)

    # ------------------------------------------------------------------
    # Selective expand — called by MainWindow after each scan
    # ------------------------------------------------------------------

    def expand_new_folders(self, new_root_nodes: list[FolderNode]) -> None:
        """
        Expand only freshly added root FolderNodes.
        Existing nodes keep whatever expanded/collapsed state the user set.
        """
        # TODO: expand more than just 1 level
        for folder in new_root_nodes:
            src_idx = self._source_model._index_for_node(folder)
            if not src_idx.isValid():
                continue
            proxy_idx = self._proxy.mapFromSource(src_idx)
            if proxy_idx.isValid():
                self.expand(proxy_idx)

    # ------------------------------------------------------------------
    # Drag-drop — accept local file/folder URLs from the OS
    # ------------------------------------------------------------------

    @staticmethod
    def _paths_from_event(event) -> list[Path]:
        """Extract valid local filesystem paths from a drag/drop event."""
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [
            Path(url.toLocalFile())
            for url in mime.urls()
            if url.isLocalFile() and url.toLocalFile()
        ]

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._paths_from_event(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._paths_from_event(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._paths_from_event(event)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # Index translation helpers
    # ------------------------------------------------------------------

    def _source_index(self, proxy_index: QModelIndex) -> QModelIndex:
        return self._proxy.mapToSource(proxy_index)

    def _node_for_proxy(self, proxy_index: QModelIndex):
        return self._source_model.node_for_index(self._source_index(proxy_index))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_clicked(self, proxy_index: QModelIndex) -> None:
        """Single click on the status icon column opens the log viewer."""
        if proxy_index.column() != Col.STATUS:
            return
        node = self._node_for_proxy(proxy_index)
        if isinstance(node, FileNode) and node.status is not None:
            self.status_clicked.emit(node)

    def _on_double_clicked(self, proxy_index: QModelIndex) -> None:
        """
        File double-click:
          SUCCESS / WARNING → open the output EPUB
          FAILURE           → open log viewer
          not yet converted → open source FB2
        Folder double-click → open directory.
        """
        node = self._node_for_proxy(proxy_index)
        if isinstance(node, FileNode):
            if node.status in (ConversionStatus.SUCCESS, ConversionStatus.WARNING):
                self.open_epub_requested.emit(node.path)
            elif node.status == ConversionStatus.FAILURE:
                self.status_clicked.emit(node)
            else:
                # if status is None (not yet converted)
                self.open_fb2_requested.emit(node.path)
        elif isinstance(node, FolderNode):
            self.folder_double_clicked.emit(node.path)

    def _on_context_menu(self, pos) -> None:
        proxy_index = self.indexAt(pos)
        node = self._node_for_proxy(proxy_index)
        menu = QMenu(self)

        if isinstance(node, FileNode):
            if node.status is not None:
                act = menu.addAction(t("ctx.open_epub"))
                act.triggered.connect(
                    lambda _=False, p=node.path: self.open_epub_requested.emit(p)
                )
            act = menu.addAction(t("ctx.open_fb2"))
            act.triggered.connect(
                lambda _=False, p=node.path: self.open_fb2_requested.emit(p)
            )
            act = menu.addAction(t("ctx.open_folder"))
            act.triggered.connect(
                lambda _=False, p=node.path.parent: self.open_folder_requested.emit(p)
            )
            if node.status is not None:
                menu.addSeparator()
                act = menu.addAction(t("ctx.view_log"))
                act.triggered.connect(lambda _=False, n=node: self.status_clicked.emit(n))
            menu.addSeparator()

        elif isinstance(node, FolderNode):
            act = menu.addAction(t("ctx.open_folder"))
            act.triggered.connect(
                lambda _=False, p=node.path: self.open_folder_requested.emit(p)
            )
            menu.addSeparator()

        remove_act = menu.addAction(t("ctx.remove"))
        remove_act.triggered.connect(self.selection_remove_requested)
        if not proxy_index.isValid():
            remove_act.setEnabled(False)

        menu.exec(self.viewport().mapToGlobal(pos))

    @override
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.selection_remove_requested.emit()
        else:
            super().keyPressEvent(event)

    def _on_language_changed(self) -> None:
        self._source_model.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, len(Col) - 1
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_source_indices(self) -> list[QModelIndex]:
        """
        Return the source-model indices (col 0) for all selected rows.
        Used by MainWindow when removing nodes.
        """
        return [
            self._source_index(idx) for idx in self.selectedIndexes() if idx.column() == 0
        ]
