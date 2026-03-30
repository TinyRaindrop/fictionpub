"""
Modal dialog for editing ConversionConfig.
Returns the new config via .result after exec().
Supports runtime language switching.

CSS section
-----------
A "Use default stylesheet" checkbox controls whether the custom-path row
is shown.  When the checkbox is checked the built-in stylesheet is used
(custom_stylesheet = None).  A "View Default" button is always available
so the user can inspect (read-only) the built-in CSS.  When using a
custom file, a "View / Edit" button opens the file in an editable viewer.
"""

import dataclasses
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...models.conversion import ConversionConfig
from ...resources.loader import get_css_path
from ..i18n import register_listener, t
from .css_viewer_dialog import CSSViewerDialog


class SettingsDialog(QDialog):
    def __init__(self, config: ConversionConfig, parent=None):
        super().__init__(parent)
        self.setFixedWidth(460)
        self._config = config
        self.result: ConversionConfig | None = None
        self._build_ui()
        self._load(config)
        register_listener(self._retranslate_ui)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        # --- Document Structure ---
        self._struct_group = QGroupBox()
        self._struct_form  = QFormLayout(self._struct_group)
        self._struct_form.setSpacing(8)

        self._toc_depth_label = QLabel()
        self._toc_depth = QSpinBox()
        self._toc_depth.setRange(1, 6)
        self._struct_form.addRow(self._toc_depth_label, self._toc_depth)

        self._split_level_label = QLabel()
        self._split_level = QSpinBox()
        self._split_level.setRange(1, 6)
        self._struct_form.addRow(self._split_level_label, self._split_level)

        self._split_size_label = QLabel()
        self._split_size = QSpinBox()
        self._split_size.setRange(0, 99999)
        self._struct_form.addRow(self._split_size_label, self._split_size)

        outer.addWidget(self._struct_group)

        # --- Processing ---
        self._proc_group = QGroupBox()
        proc_layout = QVBoxLayout(self._proc_group)

        self._remove_images = QCheckBox()
        proc_layout.addWidget(self._remove_images)

        # Typography — in-development placeholder
        from PySide6.QtWidgets import QComboBox
        typ_row = QHBoxLayout()
        self._typography_label = QLabel()
        typ_row.addWidget(self._typography_label)
        self._typography_combo = QComboBox()
        self._typography_combo.setEnabled(False)
        typ_row.addWidget(self._typography_combo)
        self._typography_badge = QLabel()
        self._typography_badge.setStyleSheet(
            "color: #888; font-style: italic; font-size: 10px;"
        )
        typ_row.addWidget(self._typography_badge)
        typ_row.addStretch()
        proc_layout.addLayout(typ_row)

        outer.addWidget(self._proc_group)

        # --- Output ---
        self._out_group = QGroupBox()
        out_form = QFormLayout(self._out_group)
        out_form.setSpacing(8)

        # -- CSS sub-section --
        self._css_label = QLabel()

        # Container that holds both the toggle row and the custom-path row.
        # Using a single container widget keeps the form-row label aligned
        # regardless of how many inner rows are visible.
        css_container = QWidget()
        css_vbox = QVBoxLayout(css_container)
        css_vbox.setContentsMargins(0, 0, 0, 0)
        css_vbox.setSpacing(3)

        # Row 1: "Use default" checkbox  +  "View Default" button
        default_row = QHBoxLayout()
        default_row.setContentsMargins(0, 0, 0, 0)
        self._use_default_css = QCheckBox()
        self._view_default_btn = QPushButton()
        self._view_default_btn.setFixedWidth(110)
        self._view_default_btn.clicked.connect(self._open_default_css)
        default_row.addWidget(self._use_default_css)
        default_row.addStretch()
        default_row.addWidget(self._view_default_btn)
        css_vbox.addLayout(default_row)

        # Row 2: custom path field  +  browse  +  view/edit
        # This whole widget is shown/hidden by the checkbox.
        self._css_custom_widget = QWidget()
        custom_row = QHBoxLayout(self._css_custom_widget)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(4)
        self._css = QLineEdit()
        self._css.setClearButtonEnabled(True)
        css_browse = QPushButton("…")
        css_browse.setFixedWidth(28)
        css_browse.clicked.connect(self._browse_css)
        self._view_edit_btn = QPushButton()
        self._view_edit_btn.setFixedWidth(110)
        self._view_edit_btn.clicked.connect(self._open_custom_css)
        custom_row.addWidget(self._css)
        custom_row.addWidget(css_browse)
        custom_row.addWidget(self._view_edit_btn)
        css_vbox.addWidget(self._css_custom_widget)

        out_form.addRow(self._css_label, css_container)

        # -- Output folder --
        self._out_path_label = QLabel()
        out_path_row = QHBoxLayout()
        self._out_path = QLineEdit()
        self._out_path.setClearButtonEnabled(True)
        out_browse = QPushButton("…")
        out_browse.setFixedWidth(28)
        out_browse.clicked.connect(self._browse_output)
        out_path_row.addWidget(self._out_path)
        out_path_row.addWidget(out_browse)
        out_form.addRow(self._out_path_label, out_path_row)

        outer.addWidget(self._out_group)

        # --- Performance ---
        self._perf_group = QGroupBox()
        perf_form = QFormLayout(self._perf_group)
        self._threads_label = QLabel()
        self._threads = QSpinBox()
        self._threads.setRange(0, 64)
        perf_form.addRow(self._threads_label, self._threads)
        outer.addWidget(self._perf_group)

        # --- Dialog buttons ---
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        # -- Signals --
        self._use_default_css.toggled.connect(self._on_css_toggle)
        self._css.textChanged.connect(self._sync_view_edit_btn)

        self._retranslate_ui()

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("settings.title"))
        self._struct_group.setTitle(t("settings.structure"))
        self._proc_group.setTitle(t("settings.processing"))
        self._out_group.setTitle(t("settings.output"))
        self._perf_group.setTitle(t("settings.performance"))

        # Structure
        self._toc_depth_label.setText(t("settings.toc_depth"))
        self._toc_depth.setToolTip(t("settings.toc_depth_tip"))
        self._split_level_label.setText(t("settings.split_level"))
        self._split_level.setToolTip(t("settings.split_level_tip"))
        self._split_size_label.setText(t("settings.split_size"))
        self._split_size.setToolTip(t("settings.split_size_tip"))
        self._split_size.setSpecialValueText(t("settings.split_size_off"))
        self._split_size.setSuffix(t("settings.split_size_unit"))

        # Processing
        self._remove_images.setText(t("settings.remove_images"))
        self._remove_images.setToolTip(t("settings.remove_images_tip"))
        self._typography_label.setText(t("settings.typography"))
        self._typography_badge.setText(t("settings.typography_wip"))
        self._typography_combo.setToolTip(t("settings.typography_wip_tip"))
        self._typography_combo.clear()
        self._typography_combo.addItem(t("settings.typography_off"))

        # Output — CSS
        self._css_label.setText(t("settings.custom_css"))
        self._use_default_css.setText(t("settings.use_default_css"))
        self._use_default_css.setToolTip(t("tooltip.use_default_css"))
        self._view_default_btn.setText(t("settings.view_default_css"))
        self._view_default_btn.setToolTip(t("tooltip.view_default_css"))
        self._css.setPlaceholderText(t("settings.css_path_hint"))
        self._view_edit_btn.setText(t("settings.view_edit_css"))
        self._view_edit_btn.setToolTip(t("tooltip.view_edit_css"))

        # Output folder
        self._out_path_label.setText(t("settings.output_folder"))
        self._out_path.setPlaceholderText(t("settings.output_placeholder"))

        # Performance
        self._threads_label.setText(t("settings.threads"))
        self._threads.setToolTip(t("settings.threads_tip"))
        self._threads.setSpecialValueText(t("settings.threads_auto"))

    # ------------------------------------------------------------------
    # Load / save config
    # ------------------------------------------------------------------

    def _load(self, cfg: ConversionConfig) -> None:
        self._toc_depth.setValue(cfg.toc_depth)
        self._split_level.setValue(cfg.split_level)
        self._split_size.setValue(cfg.split_size_kb)
        self._remove_images.setChecked(cfg.remove_unused_images)
        self._threads.setValue(cfg.num_threads)
        self._out_path.setText(str(cfg.output_path) if cfg.output_path else "")

        # CSS: if no custom stylesheet is configured → use default
        use_default = cfg.custom_stylesheet is None
        self._css.setText(str(cfg.custom_stylesheet) if cfg.custom_stylesheet else "")
        # setChecked triggers toggled → _on_css_toggle, which updates visibility
        self._use_default_css.setChecked(use_default)
        self._sync_view_edit_btn()

    def _on_ok(self) -> None:
        if self._use_default_css.isChecked():
            css_path: Path | None = None
        else:
            css_text = self._css.text().strip()
            css_path = Path(css_text) if css_text else None

        out_text = self._out_path.text().strip()
        self.result = dataclasses.replace(
            self._config,
            toc_depth            = self._toc_depth.value(),
            split_level          = self._split_level.value(),
            split_size_kb        = self._split_size.value(),
            remove_unused_images = self._remove_images.isChecked(),
            improve_typography   = False,   # in-development; always off
            custom_stylesheet    = css_path,
            output_path          = Path(out_text) if out_text else None,
            num_threads          = self._threads.value(),
        )
        self.accept()

    # ------------------------------------------------------------------
    # CSS toggle & viewer helpers
    # ------------------------------------------------------------------

    def _on_css_toggle(self, use_default: bool) -> None:
        """Show/hide the custom-path row based on the checkbox state."""
        self._css_custom_widget.setVisible(not use_default)

    def _sync_view_edit_btn(self) -> None:
        """Enable the View/Edit button only when a path has been entered."""
        self._view_edit_btn.setEnabled(bool(self._css.text().strip()))

    def _open_default_css(self) -> None:
        """Open the built-in default stylesheet in a read-only viewer."""
        path = get_css_path("default.css")
        CSSViewerDialog(
            path,
            editable=False,
            title=t("cssviewer.title_default"),
            parent=self,
        ).show()

    def _open_custom_css(self) -> None:
        """Open the currently configured custom CSS file in an editable viewer."""
        css_text = self._css.text().strip()
        if not css_text:
            return
        path = Path(css_text)
        CSSViewerDialog(
            path,
            editable=True,
            title=t("cssviewer.title_custom", name=path.name),
            parent=self,
        ).show()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_css(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("settings.custom_css"),
            self._css.text() or "",
            f"{t('filter.css')};;{t('filter.all')}",
        )
        if path:
            self._css.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            t("settings.output_folder"),
            self._out_path.text() or "",
        )
        if path:
            self._out_path.setText(path)