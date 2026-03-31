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
      – digit runs sorted numerically (21 before 200)
      – Ukrainian ґ ordered after г, not after я

Dynamic sort is disabled so the sort order is stable during conversion
(re-sorts only on header click).

Initial default sort is COL_NAME ascending so the sort indicator is on
the Name column and there is no ambiguity about the arrow on COL_STATUS.
COL_STATUS is set to Fixed resize mode so the narrow icon column cannot
be inadvertently dragged wider.

Click behaviour
───────────────
Single click  COL_STATUS → open log viewer
Double click  FileNode   → open EPUB (SUCCESS/WARNING) or log (FAILURE)
Double click  FolderNode → open directory in file manager

Selective expand
────────────────
expandNewFolders(nodes) expands only freshly added root FolderNodes;
existing expand state is preserved.
"""

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeView

from ..models.conversion import ConversionStatus
from .i18n import register_listener, t
from .models.collation import natural_collation_key
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import (
    COL_NAME,
    COL_STATUS,
    COLUMNS,
    FileTreeModel,
)

_COL_NAME_MIN = 120  # px — filename col is never auto-shrunk below this
_COL_STATUS_W = 36  # px — fixed status column width


# ─────────────────────────────────────────────────────────────────────────────


class NaturalSortProxyModel(QSortFilterProxyModel):
    """
    Proxy model with natural + Ukrainian collation sort order.

    lessThan() is fully manual so setSortRole() is irrelevant here; we
    leave the role at the default DisplayRole but never call the base
    implementation's data fetch.
    """

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        col = left.column()

        left_node = model.nodeForIndex(left)
        right_node = model.nodeForIndex(right)

        # ── Folders always sort before files at the same level ────────────
        left_folder = isinstance(left_node, FolderNode)
        right_folder = isinstance(right_node, FolderNode)
        if left_folder != right_folder:
            return left_folder  # folder < file  →  True when left is folder

        # ── Status column: integer sort key stored in UserRole ────────────
        if col == COL_STATUS:
            lv = model.data(left, Qt.ItemDataRole.UserRole) or 0
            rv = model.data(right, Qt.ItemDataRole.UserRole) or 0
            return int(lv) < int(rv)

        # ── All other columns: natural + Ukrainian collation ──────────────
        ld = model.data(left, Qt.ItemDataRole.DisplayRole) or ""
        rd = model.data(right, Qt.ItemDataRole.DisplayRole) or ""
        if isinstance(ld, str) and isinstance(rd, str):
            return natural_collation_key(ld) < natural_collation_key(rd)

        return super().lessThan(left, right)


# ─────────────────────────────────────────────────────────────────────────────


class FileTreeView(QTreeView):
    statusClicked = Signal(object)  # FileNode
    folderDoubleClicked = Signal(object)  # Path
    openEpubRequested = Signal(object)  # Path
    openFb2Requested = Signal(object)  # Path
    openFolderRequested = Signal(object)  # Path
    selectionRemoveRequested = Signal()

    def __init__(self, model: FileTreeModel, parent=None):
        super().__init__(parent)
        self._source_model = model

        self._proxy = NaturalSortProxyModel(self)
        self._proxy.setSourceModel(model)
        self._proxy.setDynamicSortFilter(False)  # re-sort only on header click

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

        # Default: all columns interactive
        for col in range(COLUMNS):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Status column: fixed width, not user-resizable
        h.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_STATUS, _COL_STATUS_W)

        # Initial widths for the other columns
        h.resizeSection(COL_NAME, 320)
        h.resizeSection(2, 160)  # Author
        h.resizeSection(3, 200)  # Title
        h.resizeSection(4, 70)  # Date
        h.resizeSection(5, 50)  # Lang

        # Sort by Name ascending on startup.
        # COL_STATUS is NOT used as the default sort to avoid the sort arrow
        # obscuring the narrow status column header.
        self.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)

    # ------------------------------------------------------------------
    # Window resize: COL_NAME auto-fills remaining viewport width
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fill_name_column()

    def _fill_name_column(self) -> None:
        h = self.header()
        vp_width = self.viewport().width()
        # Sum all columns except COL_NAME (which absorbs the remaining space)
        other_sum = sum(h.sectionSize(c) for c in range(COLUMNS) if c != COL_NAME)
        new_w = max(_COL_NAME_MIN, vp_width - other_sum)

        # blockSignals prevents the programmatic resize from being treated as
        # a user drag and from triggering any connected sectionResized slots.
        h.blockSignals(True)
        h.resizeSection(COL_NAME, new_w)
        h.blockSignals(False)

    # ------------------------------------------------------------------
    # Selective expand — called by MainWindow after each scan
    # ------------------------------------------------------------------

    def expandNewFolders(self, new_root_nodes: list[FolderNode]) -> None:
        """
        Expand only freshly added root FolderNodes.
        Existing nodes keep whatever expanded/collapsed state the user set.
        """
        for folder in new_root_nodes:
            src_idx = self._source_model._index_for_node(folder)
            if not src_idx.isValid():
                continue
            proxy_idx = self._proxy.mapFromSource(src_idx)
            if proxy_idx.isValid():
                self.expand(proxy_idx)

    # ------------------------------------------------------------------
    # Index translation helpers
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
        node = self._node_for_proxy(proxy_index)
        menu = QMenu(self)

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
                act.triggered.connect(lambda _=False, n=node: self.statusClicked.emit(n))
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
        self._source_model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, COLUMNS - 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selectedSourceIndices(self) -> list[QModelIndex]:
        """
        Return the source-model indices (col 0) for all selected rows.
        Used by MainWindow when removing nodes.
        """
        return [
            self._source_index(idx) for idx in self.selectedIndexes() if idx.column() == 0
        ]
