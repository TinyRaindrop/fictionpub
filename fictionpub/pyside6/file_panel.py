"""
FileTreeView — QTreeView configured for the file list.

Column layout (matches COL_* constants in file_tree_model.py)
  0  Filename  + checkbox
  1  Status    icon (sortable, narrow)
  2  Author
  3  Title
  4  Date
  5  Lang

Column 0 (Filename) auto-fills the remaining viewport width on window
resize; all other columns are freely draggable (Interactive mode).

Sorting
-------
A QSortFilterProxyModel sits between the source FileTreeModel and the view.
sortRole = Qt.UserRole so the status column sorts on its integer key rather
than on display text.  All source-model indices are mapped through the proxy
before being returned to callers.

Click behaviour
---------------
Single click on COL_STATUS  → open log viewer (any status)
Double click on file row    → open EPUB if SUCCESS/WARNING; log viewer if FAILURE
Double click on folder row  → open folder in file manager
"""

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeView

from .i18n import register_listener, t
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import (
    COLUMNS, COL_NAME, COL_STATUS,
    FileTreeModel,
)
from ..models.conversion import ConversionStatus

_COL_NAME_MIN = 120   # px — filename col is never auto-shrunk below this


class FileTreeView(QTreeView):
    statusClicked            = Signal(object)   # FileNode
    fileDoubleClicked        = Signal(object)   # Path
    folderDoubleClicked      = Signal(object)   # Path
    openEpubRequested        = Signal(object)   # Path (source fb2 path; caller resolves epub)
    openFb2Requested         = Signal(object)   # Path
    openFolderRequested      = Signal(object)   # Path
    selectionRemoveRequested = Signal()

    def __init__(self, model: FileTreeModel, parent=None):
        super().__init__(parent)
        self._source_model = model

        # Proxy for sorting; UserRole carries the integer sort key for COL_STATUS
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self._proxy.setDynamicSortFilter(False)   # sort only when header clicked

        self.setModel(self._proxy)
        self.setSortingEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

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

        # All Interactive: user can drag every separator, and only that column moves.
        for col in range(COLUMNS):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Initial widths
        h.resizeSection(COL_NAME,   320)
        h.resizeSection(COL_STATUS,  36)
        h.resizeSection(2,          160)   # Author
        h.resizeSection(3,          200)   # Title
        h.resizeSection(4,           70)   # Date
        h.resizeSection(5,           50)   # Lang

        # Sort by status ascending by default (failures on top)
        # TODO: why sort now? files/folders should be in alphabetical order
        self.sortByColumn(COL_STATUS, Qt.SortOrder.AscendingOrder)

    # ------------------------------------------------------------------
    # Window resize: only col 0 auto-fills, never on user column drags
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fill_name_column()

    def _fill_name_column(self) -> None:
        h = self.header()
        vp_width = self.viewport().width()
        # Sum all columns except COL_NAME (which absorbs the remaining space)
        other_sum = sum(
            h.sectionSize(c) for c in range(COLUMNS) if c != COL_NAME
        )
        new_w = max(_COL_NAME_MIN, vp_width - other_sum)

        # blockSignals prevents the programmatic resize from being treated as
        # a user drag and from triggering any connected sectionResized slots.
        h.blockSignals(True)
        h.resizeSection(COL_NAME, new_w)
        h.blockSignals(False)

    # ------------------------------------------------------------------
    # Index translation: proxy → source
    # ------------------------------------------------------------------

    def _source_index(self, proxy_index: QModelIndex) -> QModelIndex:
        return self._proxy.mapToSource(proxy_index)

    def _node_for_proxy(self, proxy_index: QModelIndex):
        return self._source_model.nodeForIndex(self._source_index(proxy_index))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_clicked(self, proxy_index: QModelIndex) -> None:
        """Single click on the status icon column opens the log viewer."""
        if proxy_index.column() != COL_STATUS:
            return
        node = self._node_for_proxy(proxy_index)
        if isinstance(node, FileNode) and node.status is not None:
            self.statusClicked.emit(node)

    def _on_double_clicked(self, proxy_index: QModelIndex) -> None:
        """
        File double-click:
          SUCCESS / WARNING → open the output EPUB
          FAILURE           → open log viewer
          not yet converted → no action
        Folder double-click → open directory.
        """
        node = self._node_for_proxy(proxy_index)
        if isinstance(node, FileNode):
            if node.status in (ConversionStatus.SUCCESS, ConversionStatus.WARNING):
                self.openEpubRequested.emit(node.path)
            elif node.status == ConversionStatus.FAILURE:
                self.statusClicked.emit(node)
            # no action if status is None (not yet converted)
        elif isinstance(node, FolderNode):
            self.folderDoubleClicked.emit(node.path)

    def _on_context_menu(self, pos) -> None:
        proxy_index = self.indexAt(pos)
        node        = self._node_for_proxy(proxy_index)
        menu        = QMenu(self)

        if isinstance(node, FileNode):
            if node.status is not None:
                act = menu.addAction(t("ctx.open_epub"))
                act.triggered.connect(
                    lambda _=False, p=node.path: self.openEpubRequested.emit(p)
                )

            act = menu.addAction(t("ctx.open_fb2"))
            act.triggered.connect(
                lambda _=False, p=node.path: self.openFb2Requested.emit(p)
            )

            act = menu.addAction(t("ctx.open_folder"))
            act.triggered.connect(
                lambda _=False, p=node.path.parent: self.openFolderRequested.emit(p)
            )

            if node.status is not None:
                menu.addSeparator()
                act = menu.addAction(t("ctx.view_log"))
                act.triggered.connect(
                    lambda _=False, n=node: self.statusClicked.emit(n)
                )

            menu.addSeparator()

        elif isinstance(node, FolderNode):
            act = menu.addAction(t("ctx.open_folder"))
            act.triggered.connect(
                lambda _=False, p=node.path: self.openFolderRequested.emit(p)
            )
            menu.addSeparator()

        remove_act = menu.addAction(t("ctx.remove"))
        remove_act.triggered.connect(self.selectionRemoveRequested)
        if not proxy_index.isValid():
            remove_act.setEnabled(False)

        menu.exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.selectionRemoveRequested.emit()
        else:
            super().keyPressEvent(event)

    def _on_language_changed(self) -> None:
        # Force the header to re-query translated labels
        self._source_model.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, COLUMNS - 1
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selectedSourceIndices(self) -> list[QModelIndex]:
        """
        Return the source-model indices (col 0) for all selected rows.
        Used by MainWindow when removing nodes.
        """
        return [
            self._source_index(idx)
            for idx in self.selectedIndexes()
            if idx.column() == 0
        ]