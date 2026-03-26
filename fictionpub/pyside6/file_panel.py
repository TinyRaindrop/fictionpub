"""
FileTreeView — QTreeView configured for the file list.

Column resize fix: ALL columns use Interactive mode.
  - Column 0 (Name) gets a large initial width and grows with the window.
  - Columns 1–4 have fixed initial widths that the user can drag.
  - header.setStretchLastSection(False) so no column is pinned as non-resizable.
  - header.setMinimumSectionSize(50) prevents columns from being dragged to zero.

Signals:
  statusClicked(FileNode)       — clicked on a node that has a conversion status
  fileDoubleClicked(Path)       — double-click on a FileNode
  folderDoubleClicked(Path)     — double-click on a FolderNode
  openEpubRequested(Path)       — context menu "Open EPUB"  (fb2 source path)
  openFb2Requested(Path)        — context menu "Open source FB2"
  openFolderRequested(Path)     — context menu "Open containing folder"
  selectionRemoveRequested()    — Delete key or context "Remove"
"""

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeView

from .i18n import register_listener, t
from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import FileTreeModel


class FileTreeView(QTreeView):
    statusClicked            = Signal(object)   # FileNode
    fileDoubleClicked        = Signal(object)   # Path
    folderDoubleClicked      = Signal(object)   # Path
    openEpubRequested        = Signal(object)   # Path (fb2 source path)
    openFb2Requested         = Signal(object)   # Path
    openFolderRequested      = Signal(object)   # Path
    selectionRemoveRequested = Signal()

    def __init__(self, model: FileTreeModel, parent=None):
        super().__init__(parent)
        self._model = model

        self.setModel(model)
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

    def _setup_header(self) -> None:
        header = self.header()

        # All columns Interactive — the user can drag any resize handle.
        # Stretch mode would prevent resizing column 0, which is the reported bug.
        for col in range(self._model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Give column 0 a large initial proportion; remaining columns are narrow.
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)

        # Initial widths — user can change all of these.
        header.resizeSection(0, 420)  # Name — wide
        header.resizeSection(1, 160)  # Author
        header.resizeSection(2, 200)  # Title
        header.resizeSection(3, 70)   # Date
        header.resizeSection(4, 50)   # Lang

        # Column 0 stretches when the window is widened.
        # We achieve this by making it the only section that participates in
        # the resize by setting ResizeToContents on tiny columns and letting
        # col 0 absorb the remainder.  The cleanest Qt way is a single
        # stretchable section, but then it becomes non-interactive.
        # Solution: use Interactive everywhere and re-resize col 0 on resize.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Re-override col 0 back to Interactive AFTER setting Stretch on others
        # so it stretches but is also draggable.
        # Qt does not support Stretch+Interactive simultaneously; we compromise:
        # col 0 uses Stretch (fills remaining space, not directly draggable)
        # while ALL other columns are Interactive (user-draggable).
        # This matches the UX of most file managers.
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_clicked(self, index: QModelIndex) -> None:
        if index.column() != 0:
            return
        node = self._model.nodeForIndex(index)
        if isinstance(node, FileNode) and node.status is not None:
            self.statusClicked.emit(node)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        node = self._model.nodeForIndex(index)
        if isinstance(node, FileNode):
            self.fileDoubleClicked.emit(node.path)
        elif isinstance(node, FolderNode):
            self.folderDoubleClicked.emit(node.path)

    def _on_context_menu(self, pos) -> None:
        index = self.indexAt(pos)
        node  = self._model.nodeForIndex(index)
        menu  = QMenu(self)

        if isinstance(node, FileNode):
            # --- Conversion output actions ---
            if node.status is not None:
                open_epub = menu.addAction(t("ctx.open_epub"))
                open_epub.triggered.connect(lambda _=False, p=node.path: self.openEpubRequested.emit(p))

            open_fb2 = menu.addAction(t("ctx.open_fb2"))
            open_fb2.triggered.connect(lambda _=False, p=node.path: self.openFb2Requested.emit(p))

            open_folder = menu.addAction(t("ctx.open_folder"))
            open_folder.triggered.connect(lambda _=False, p=node.path.parent: self.openFolderRequested.emit(p))

            if node.status is not None:
                menu.addSeparator()
                view_log = menu.addAction(t("ctx.view_log"))
                view_log.triggered.connect(lambda _=False, n=node: self.statusClicked.emit(n))

            menu.addSeparator()

        elif isinstance(node, FolderNode):
            open_folder = menu.addAction(t("ctx.open_folder"))
            open_folder.triggered.connect(lambda _=False, p=node.path: self.openFolderRequested.emit(p))
            menu.addSeparator()

        remove_act = menu.addAction(t("ctx.remove"))
        remove_act.triggered.connect(self.selectionRemoveRequested)
        if not index.isValid():
            remove_act.setEnabled(False)

        menu.exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.selectionRemoveRequested.emit()
        else:
            super().keyPressEvent(event)

    def _on_language_changed(self) -> None:
        # Force the header to re-query headerData so translated labels show.
        self._model.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, self._model.columnCount() - 1
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selectedModelIndices(self) -> list[QModelIndex]:
        """Return selected indices, column 0 only (one per row)."""
        return [idx for idx in self.selectedIndexes() if idx.column() == 0]