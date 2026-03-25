"""
FileTreeView — QTreeView configured for the file list.

Signals emitted by this widget:
  statusClicked(FileNode)     — user clicked column 0 of a node that has a status
  fileDoubleClicked(Path)     — double-click on a FileNode
  folderDoubleClicked(Path)   — double-click on a FolderNode
  selectionRemoveRequested()  — Delete key pressed
"""

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeView

from .models.file_node import FileNode, FolderNode
from .models.file_tree_model import FileTreeModel


class FileTreeView(QTreeView):
    statusClicked            = Signal(object)   # FileNode
    fileDoubleClicked        = Signal(object)   # Path
    folderDoubleClicked      = Signal(object)   # Path
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

        # Header
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)          # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)      # Author
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)      # Title
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Date
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Lang
        header.resizeSection(1, 160)
        header.resizeSection(2, 200)

        # Connect events
        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_clicked(self, index: QModelIndex) -> None:
        """
        For file nodes with a conversion status, emit statusClicked so the
        main window can decide whether to open the log viewer.
        Only fires when clicking column 0 to avoid false triggers.
        """
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
            if node.status is not None:
                view_log = menu.addAction("View Log")
                view_log.triggered.connect(lambda: self.statusClicked.emit(node))
                menu.addSeparator()

        remove_act = menu.addAction("Remove")
        remove_act.triggered.connect(self.selectionRemoveRequested)

        if not index.isValid():
            remove_act.setEnabled(False)

        menu.exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.selectionRemoveRequested.emit()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selectedModelIndices(self) -> list[QModelIndex]:
        """Return the list of currently selected source-model indices (column 0 only)."""
        return [
            idx for idx in self.selectedIndexes()
            if idx.column() == 0
        ]

    def expandAll(self) -> None:
        super().expandAll()
