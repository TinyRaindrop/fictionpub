"""
Modal dialog for editing ConversionConfig.
Returns the new config via .result after exec().
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
)

from ...models.conversion import ConversionConfig


class SettingsDialog(QDialog):
    def __init__(self, config: ConversionConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conversion Settings")
        self.setFixedWidth(440)
        self._config = config
        self.result: ConversionConfig | None = None
        self._build_ui()
        self._load(config)

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(12)

        # --- Structure group ---
        struct = QGroupBox("Document Structure")
        form = QFormLayout(struct)
        form.setSpacing(8)

        self._toc_depth = QSpinBox()
        self._toc_depth.setRange(1, 6)
        self._toc_depth.setToolTip("Maximum heading level to include in the table of contents.")
        form.addRow("TOC depth (1–6):", self._toc_depth)

        self._split_level = QSpinBox()
        self._split_level.setRange(1, 6)
        self._split_level.setToolTip("Split the EPUB into separate files at this heading level.")
        form.addRow("Split level (1–6):", self._split_level)

        self._split_size = QSpinBox()
        self._split_size.setRange(0, 99999)
        self._split_size.setSpecialValueText("Disabled")
        self._split_size.setSuffix(" KB")
        self._split_size.setToolTip("Raise split level if XHTML files exceed this size. 0 = disabled.")
        form.addRow("Max file size:", self._split_size)

        outer.addWidget(struct)

        # --- Processing group ---
        proc = QGroupBox("Processing")
        proc_layout = QVBoxLayout(proc)

        self._remove_images = QCheckBox("Remove unused images")
        self._remove_images.setToolTip("Strip images that are not referenced in the text.")
        proc_layout.addWidget(self._remove_images)

        self._typography = QCheckBox("Improve typography")
        self._typography.setToolTip(
            "Enable post-processing: non-breaking spaces, no-break spans, etc."
        )
        proc_layout.addWidget(self._typography)

        # Typography sub-options (enabled only when typography is checked)
        nbsp_row = QHBoxLayout()
        nbsp_row.addSpacing(20)
        nbsp_row.addWidget(QLabel("NBSP word length range:"))
        self._nbsp_min = QSpinBox(); self._nbsp_min.setRange(1, 20); self._nbsp_min.setFixedWidth(55)
        self._nbsp_max = QSpinBox(); self._nbsp_max.setRange(1, 20); self._nbsp_max.setFixedWidth(55)
        nbsp_row.addWidget(self._nbsp_min)
        nbsp_row.addWidget(QLabel("–"))
        nbsp_row.addWidget(self._nbsp_max)
        nbsp_row.addStretch()
        proc_layout.addLayout(nbsp_row)

        nobr_row = QHBoxLayout()
        nobr_row.addSpacing(20)
        nobr_row.addWidget(QLabel("No-break word length range:"))
        self._nobr_min = QSpinBox(); self._nobr_min.setRange(1, 20); self._nobr_min.setFixedWidth(55)
        self._nobr_max = QSpinBox(); self._nobr_max.setRange(1, 20); self._nobr_max.setFixedWidth(55)
        nobr_row.addWidget(self._nobr_min)
        nobr_row.addWidget(QLabel("–"))
        nobr_row.addWidget(self._nobr_max)
        nobr_row.addStretch()
        proc_layout.addLayout(nobr_row)

        self._typography.toggled.connect(self._nbsp_min.setEnabled)
        self._typography.toggled.connect(self._nbsp_max.setEnabled)
        self._typography.toggled.connect(self._nobr_min.setEnabled)
        self._typography.toggled.connect(self._nobr_max.setEnabled)

        outer.addWidget(proc)

        # --- Output group ---
        out = QGroupBox("Output")
        out_form = QFormLayout(out)
        out_form.setSpacing(8)

        css_row = QHBoxLayout()
        self._css = QLineEdit()
        self._css.setPlaceholderText("Use built-in stylesheet")
        self._css.setClearButtonEnabled(True)
        css_browse = QPushButton("…")
        css_browse.setFixedWidth(28)
        css_browse.clicked.connect(self._browse_css)
        css_row.addWidget(self._css)
        css_row.addWidget(css_browse)
        out_form.addRow("Custom CSS:", css_row)

        out_path_row = QHBoxLayout()
        self._out_path = QLineEdit()
        self._out_path.setPlaceholderText("Same folder as input file")
        self._out_path.setClearButtonEnabled(True)
        out_browse = QPushButton("…")
        out_browse.setFixedWidth(28)
        out_browse.clicked.connect(self._browse_output)
        out_path_row.addWidget(self._out_path)
        out_path_row.addWidget(out_browse)
        out_form.addRow("Output folder:", out_path_row)

        outer.addWidget(out)

        # --- Performance ---
        perf = QGroupBox("Performance")
        perf_form = QFormLayout(perf)
        self._threads = QSpinBox()
        self._threads.setRange(0, 64)
        self._threads.setSpecialValueText("Auto")
        self._threads.setToolTip("Number of parallel worker processes. 0 = auto-detect.")
        perf_form.addRow("Worker threads (0=auto):", self._threads)
        outer.addWidget(perf)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _load(self, cfg: ConversionConfig) -> None:
        self._toc_depth.setValue(cfg.toc_depth)
        self._split_level.setValue(cfg.split_level)
        self._split_size.setValue(cfg.split_size_kb)
        self._remove_images.setChecked(cfg.remove_unused_images)
        self._typography.setChecked(cfg.improve_typography)
        self._nbsp_min.setValue(cfg.word_len_nbsp_range[0])
        self._nbsp_max.setValue(cfg.word_len_nbsp_range[1])
        self._nobr_min.setValue(cfg.word_len_nobreak_range[0])
        self._nobr_max.setValue(cfg.word_len_nobreak_range[1])
        self._css.setText(str(cfg.custom_stylesheet) if cfg.custom_stylesheet else "")
        self._out_path.setText(str(cfg.output_path) if cfg.output_path else "")
        self._threads.setValue(cfg.num_threads)

        # Sync sub-option enabled state
        typ_on = cfg.improve_typography
        for w in (self._nbsp_min, self._nbsp_max, self._nobr_min, self._nobr_max):
            w.setEnabled(typ_on)

    def _on_ok(self) -> None:
        css_text = self._css.text().strip()
        out_text = self._out_path.text().strip()
        self.result = dataclasses.replace(
            self._config,
            toc_depth              = self._toc_depth.value(),
            split_level            = self._split_level.value(),
            split_size_kb          = self._split_size.value(),
            remove_unused_images   = self._remove_images.isChecked(),
            improve_typography     = self._typography.isChecked(),
            word_len_nbsp_range    = (self._nbsp_min.value(), self._nbsp_max.value()),
            word_len_nobreak_range = (self._nobr_min.value(), self._nobr_max.value()),
            custom_stylesheet      = Path(css_text) if css_text else None,
            output_path            = Path(out_text) if out_text else None,
            num_threads            = self._threads.value(),
        )
        self.accept()

    def _browse_css(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSS File", "", "CSS Files (*.css);;All Files (*)"
        )
        if path:
            self._css.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self._out_path.setText(path)
