"""
Modal dialog for editing ConversionConfig.
Returns the new config via .result after exec().
Supports runtime language switching.
"""

import dataclasses
from pathlib import Path

from PySide6.QtWidgets import (
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
    QSpinBox,
    QVBoxLayout,
)

from ...models.conversion import ConversionConfig
from ..i18n import register_listener, t


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

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        # --- Structure ---
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
        self._proc_group  = QGroupBox()
        proc_layout = QVBoxLayout(self._proc_group)

        self._remove_images = QCheckBox()
        proc_layout.addWidget(self._remove_images)

        # Typography — in-development placeholder
        # Shown as a disabled QComboBox so it's clearly not yet selectable
        typ_row = QHBoxLayout()
        self._typography_label = QLabel()
        typ_row.addWidget(self._typography_label)
        self._typography_combo = QComboBox()
        self._typography_combo.setEnabled(False)
        self._typography_combo.setToolTip("")   # set in _retranslate_ui
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

        self._css_label = QLabel()
        css_row = QHBoxLayout()
        self._css = QLineEdit()
        self._css.setClearButtonEnabled(True)
        css_browse = QPushButton("…")
        css_browse.setFixedWidth(28)
        css_browse.clicked.connect(self._browse_css)
        css_row.addWidget(self._css)
        css_row.addWidget(css_browse)
        out_form.addRow(self._css_label, css_row)

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

        # --- Buttons ---
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_ok)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("settings.title"))
        self._struct_group.setTitle(t("settings.structure"))
        self._proc_group.setTitle(t("settings.processing"))
        self._out_group.setTitle(t("settings.output"))
        self._perf_group.setTitle(t("settings.performance"))

        # Structure labels and tooltips
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

        # Typography — in-development, always disabled
        self._typography_label.setText(t("settings.typography"))
        self._typography_badge.setText(t("settings.typography_wip"))
        self._typography_combo.setToolTip(t("settings.typography_wip_tip"))
        # Repopulate combo items with translated text each time language changes
        self._typography_combo.clear()
        self._typography_combo.addItem(t("settings.typography_off"))

        # Output
        self._css_label.setText(t("settings.custom_css"))
        self._css.setPlaceholderText(t("settings.css_placeholder"))
        self._out_path_label.setText(t("settings.output_folder"))
        self._out_path.setPlaceholderText(t("settings.output_placeholder"))

        # Performance
        self._threads_label.setText(t("settings.threads"))
        self._threads.setToolTip(t("settings.threads_tip"))
        self._threads.setSpecialValueText(t("settings.threads_auto"))

    def _load(self, cfg: ConversionConfig) -> None:
        self._toc_depth.setValue(cfg.toc_depth)
        self._split_level.setValue(cfg.split_level)
        self._split_size.setValue(cfg.split_size_kb)
        self._remove_images.setChecked(cfg.remove_unused_images)
        # self._typography.setChecked(cfg.improve_typography)
        # self._nbsp_min.setValue(cfg.word_len_nbsp_range[0])
        # self._nbsp_max.setValue(cfg.word_len_nbsp_range[1])
        # self._nobr_min.setValue(cfg.word_len_nobreak_range[0])
        # self._nobr_max.setValue(cfg.word_len_nobreak_range[1])
        self._css.setText(str(cfg.custom_stylesheet) if cfg.custom_stylesheet else "")
        self._out_path.setText(str(cfg.output_path) if cfg.output_path else "")
        self._threads.setValue(cfg.num_threads)

        # typ_on = cfg.improve_typography
        # for w in (self._nbsp_min, self._nbsp_max, self._nobr_min, self._nobr_max):
            # w.setEnabled(typ_on)

    def _on_ok(self) -> None:
        css_text = self._css.text().strip()
        out_text = self._out_path.text().strip()
        self.result = dataclasses.replace(
            self._config,
            toc_depth              = self._toc_depth.value(),
            split_level            = self._split_level.value(),
            split_size_kb          = self._split_size.value(),
            remove_unused_images   = self._remove_images.isChecked(),
            improve_typography     = False,    # in-development; always off
            custom_stylesheet      = Path(css_text) if css_text else None,
            output_path            = Path(out_text) if out_text else None,
            num_threads            = self._threads.value(),
        )
        self.accept()

    def _browse_css(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, t("settings.custom_css"), "",
            f"{t('filter.css')};;{t('filter.all')}"
        )
        if path:
            self._css.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("settings.output_folder"))
        if path:
            self._out_path.setText(path)