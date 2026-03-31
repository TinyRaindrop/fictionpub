"""
fictionpub/pyside6/dialogs/settings_dialog.py

Modal dialog for editing ConversionConfig.
Returns the new config via .result after exec().
Supports runtime language switching.

Stylesheet section
------------------
Two always-visible radio buttons:
  ○ Default stylesheet                     [View Default]
  ● Custom stylesheet:
    [______path______] [...]  [View / Edit]

The path row + View/Edit button are enabled only when the Custom radio
is selected.  View Default is always enabled.

Output section
--------------
Two always-visible radio buttons:
  ○ Same folder as source file
  ● All outputs to folder:
    [______path______] [...]
    □ Retain original folder structure

The path row and the checkbox are enabled only when the second radio is
selected.

Keeping all widgets visible at all times means the dialog never resizes
when the user switches modes — only the enabled state changes.
"""

import dataclasses
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from ...models.conversion import ConversionConfig
from ...resources.loader import get_css_path
from ..i18n import register_listener, t
from .css_viewer_dialog import CSSViewerDialog


class SettingsDialog(QDialog):
    def __init__(self, config: ConversionConfig, parent=None):
        super().__init__(parent)
        self.setFixedWidth(480)
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

        outer.addWidget(self._build_structure_group())
        outer.addWidget(self._build_processing_group())
        outer.addWidget(self._build_stylesheet_group())
        outer.addWidget(self._build_output_group())
        outer.addWidget(self._build_performance_group())

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._retranslate_ui()

    # ── Group builders ─────────────────────────────────────────────────

    def _build_structure_group(self) -> QGroupBox:
        self._struct_group = QGroupBox()
        form = QFormLayout(self._struct_group)
        form.setSpacing(8)

        self._toc_depth_label = QLabel()
        self._toc_depth = QSpinBox()
        self._toc_depth.setRange(1, 6)
        form.addRow(self._toc_depth_label, self._toc_depth)

        self._split_level_label = QLabel()
        self._split_level = QSpinBox()
        self._split_level.setRange(1, 6)
        form.addRow(self._split_level_label, self._split_level)

        self._split_size_label = QLabel()
        self._split_size = QSpinBox()
        self._split_size.setRange(0, 99999)
        form.addRow(self._split_size_label, self._split_size)

        return self._struct_group

    def _build_processing_group(self) -> QGroupBox:
        self._proc_group = QGroupBox()
        layout = QVBoxLayout(self._proc_group)

        self._remove_images = QCheckBox()
        layout.addWidget(self._remove_images)

        # Typography — in-development placeholder
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
        layout.addLayout(typ_row)

        return self._proc_group

    def _build_stylesheet_group(self) -> QGroupBox:
        """
        Radio buttons (always both visible):
          ○ Default stylesheet                          [View Default]
          ● Custom stylesheet:
            [_______path_______] [...]   [View / Edit]
        """
        self._css_group = QGroupBox()
        layout = QVBoxLayout(self._css_group)
        layout.setSpacing(4)

        self._css_btn_group = QButtonGroup(self)

        # ── Row 0: default radio + View Default button ───────────────
        row0 = QHBoxLayout()
        self._css_default_radio = QRadioButton()
        self._css_btn_group.addButton(self._css_default_radio, 0)
        row0.addWidget(self._css_default_radio)
        row0.addStretch()
        self._view_default_btn = QPushButton()
        self._view_default_btn.setFixedWidth(118)
        self._view_default_btn.clicked.connect(self._open_default_css)
        row0.addWidget(self._view_default_btn)
        layout.addLayout(row0)

        # ── Row 1: custom radio ───────────────────────────────────────
        self._css_custom_radio = QRadioButton()
        self._css_btn_group.addButton(self._css_custom_radio, 1)
        layout.addWidget(self._css_custom_radio)

        # ── Row 2: custom path + browse + view/edit ───────────────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(20, 0, 0, 0)  # visual indent under the radio
        self._css = QLineEdit()
        self._css.setClearButtonEnabled(True)
        row2.addWidget(self._css)
        self._css_browse = QPushButton("…")
        self._css_browse.setFixedWidth(28)
        self._css_browse.clicked.connect(self._browse_css)
        row2.addWidget(self._css_browse)
        self._view_edit_btn = QPushButton()
        self._view_edit_btn.setFixedWidth(118)
        self._view_edit_btn.clicked.connect(self._open_custom_css)
        row2.addWidget(self._view_edit_btn)
        layout.addLayout(row2)

        # ── Signals ───────────────────────────────────────────────────
        self._css_btn_group.idToggled.connect(self._on_css_radio_changed)
        self._css.textChanged.connect(self._sync_view_edit_btn)

        return self._css_group

    def _build_output_group(self) -> QGroupBox:
        """
        Radio buttons (always both visible):
          ○ Same folder as source file
          ● All outputs to folder:
            [_______path_______] [...]
            □ Retain original folder structure
        """
        self._out_group = QGroupBox()
        layout = QVBoxLayout(self._out_group)
        layout.setSpacing(4)

        self._out_btn_group = QButtonGroup(self)

        # ── Row 0: same-folder radio ──────────────────────────────────
        self._out_same_radio = QRadioButton()
        self._out_btn_group.addButton(self._out_same_radio, 0)
        layout.addWidget(self._out_same_radio)

        # ── Row 1: specified-folder radio ─────────────────────────────
        self._out_folder_radio = QRadioButton()
        self._out_btn_group.addButton(self._out_folder_radio, 1)
        layout.addWidget(self._out_folder_radio)

        # ── Row 2: path + browse ──────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(20, 0, 0, 0)
        self._out_path = QLineEdit()
        self._out_path.setClearButtonEnabled(True)
        row2.addWidget(self._out_path)
        out_browse = QPushButton("…")
        out_browse.setFixedWidth(28)
        out_browse.clicked.connect(self._browse_output)
        row2.addWidget(out_browse)
        layout.addLayout(row2)

        # ── Row 3: retain structure checkbox ──────────────────────────
        row3 = QHBoxLayout()
        row3.setContentsMargins(20, 0, 0, 0)
        self._retain_structure = QCheckBox()
        row3.addWidget(self._retain_structure)
        row3.addStretch()
        layout.addLayout(row3)

        # Collect all widgets that are enabled/disabled together
        self._out_custom_widgets = [self._out_path, out_browse, self._retain_structure]

        self._out_btn_group.idToggled.connect(self._on_out_radio_changed)

        return self._out_group

    def _build_performance_group(self) -> QGroupBox:
        self._perf_group = QGroupBox()
        form = QFormLayout(self._perf_group)
        self._threads_label = QLabel()
        self._threads = QSpinBox()
        self._threads.setRange(0, 64)
        form.addRow(self._threads_label, self._threads)
        return self._perf_group

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("settings.title"))

        # Structure
        self._struct_group.setTitle(t("settings.structure"))
        self._toc_depth_label.setText(t("settings.toc_depth"))
        self._toc_depth.setToolTip(t("settings.toc_depth_tip"))
        self._split_level_label.setText(t("settings.split_level"))
        self._split_level.setToolTip(t("settings.split_level_tip"))
        self._split_size_label.setText(t("settings.split_size"))
        self._split_size.setToolTip(t("settings.split_size_tip"))
        self._split_size.setSpecialValueText(t("settings.split_size_off"))
        self._split_size.setSuffix(t("settings.split_size_unit"))

        # Processing
        self._proc_group.setTitle(t("settings.processing"))
        self._remove_images.setText(t("settings.remove_images"))
        self._remove_images.setToolTip(t("settings.remove_images_tip"))
        self._typography_label.setText(t("settings.typography"))
        self._typography_badge.setText(t("settings.typography_wip"))
        self._typography_combo.setToolTip(t("settings.typography_wip_tip"))
        self._typography_combo.clear()
        self._typography_combo.addItem(t("settings.typography_off"))

        # Stylesheet
        self._css_group.setTitle(t("settings.stylesheet_group"))
        self._css_default_radio.setText(t("settings.css_default"))
        self._css_default_radio.setToolTip(t("tooltip.css_default"))
        self._view_default_btn.setText(t("settings.view_default_css"))
        self._view_default_btn.setToolTip(t("tooltip.view_default_css"))
        self._css_custom_radio.setText(t("settings.css_custom"))
        self._css.setPlaceholderText(t("settings.css_path_hint"))
        self._view_edit_btn.setText(t("settings.view_edit_css"))
        self._view_edit_btn.setToolTip(t("tooltip.view_edit_css"))

        # Output
        self._out_group.setTitle(t("settings.output"))
        self._out_same_radio.setText(t("settings.out_same_folder"))
        self._out_folder_radio.setText(t("settings.out_to_folder"))
        self._out_path.setPlaceholderText(t("settings.output_placeholder"))
        self._retain_structure.setText(t("settings.retain_structure"))
        self._retain_structure.setToolTip(t("tooltip.retain_structure"))

        # Performance
        self._perf_group.setTitle(t("settings.performance"))
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

        # CSS — trigger radio → _on_css_radio_changed → enable/disable
        if cfg.custom_stylesheet:
            self._css_custom_radio.setChecked(True)
            self._css.setText(str(cfg.custom_stylesheet))
        else:
            self._css_default_radio.setChecked(True)
            self._css.clear()

        # Output — trigger radio → _on_out_radio_changed → enable/disable
        if cfg.output_path:
            self._out_folder_radio.setChecked(True)
            self._out_path.setText(str(cfg.output_path))
        else:
            self._out_same_radio.setChecked(True)
            self._out_path.clear()

        self._retain_structure.setChecked(cfg.retain_folder_structure)

        # Force sync of dependent button states
        self._sync_view_edit_btn()

    def _on_ok(self) -> None:
        # CSS
        if self._css_default_radio.isChecked():
            css_path: Path | None = None
        else:
            text = self._css.text().strip()
            css_path = Path(text) if text else None

        # Output path
        if self._out_same_radio.isChecked():
            out_path: Path | None = None
            retain = False
        else:
            text = self._out_path.text().strip()
            out_path = Path(text) if text else None
            retain = self._retain_structure.isChecked()

        self.result = dataclasses.replace(
            self._config,
            toc_depth=self._toc_depth.value(),
            split_level=self._split_level.value(),
            split_size_kb=self._split_size.value(),
            remove_unused_images=self._remove_images.isChecked(),
            improve_typography=False,  # in-development; always off
            custom_stylesheet=css_path,
            output_path=out_path,
            retain_folder_structure=retain,
            num_threads=self._threads.value(),
        )
        self.accept()

    # ------------------------------------------------------------------
    # Radio / toggle handlers
    # ------------------------------------------------------------------

    def _on_css_radio_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        custom_active = btn_id == 1
        self._css.setEnabled(custom_active)
        self._css_browse.setEnabled(custom_active)
        self._sync_view_edit_btn()

    def _on_out_radio_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        folder_active = btn_id == 1
        for w in self._out_custom_widgets:
            w.setEnabled(folder_active)

    def _sync_view_edit_btn(self) -> None:
        """Enable View/Edit only when the custom radio is selected and a path is present."""
        self._view_edit_btn.setEnabled(
            self._css_custom_radio.isChecked() and bool(self._css.text().strip())
        )

    # ------------------------------------------------------------------
    # CSS viewer helpers
    # ------------------------------------------------------------------

    def _open_default_css(self) -> None:
        path = get_css_path("default.css")
        CSSViewerDialog(
            path,
            editable=False,
            title=t("cssviewer.title_default"),
            parent=self,
        ).show()

    def _open_custom_css(self) -> None:
        text = self._css.text().strip()
        if not text:
            return
        path = Path(text)
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
            t("settings.css_custom"),
            self._css.text() or "",
            f"{t('filter.css')};;{t('filter.all')}",
        )
        if path:
            self._css.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            t("settings.output"),
            self._out_path.text() or "",
        )
        if path:
            self._out_path.setText(path)
