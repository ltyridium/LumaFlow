from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QGroupBox,
    QSpinBox,
    QPushButton,
)
from PySide6.QtCore import Signal

from core.i18n import tr


class AudioControlsWidget(QWidget):
    """User controls for audio visualization settings."""

    visibility_changed = Signal(str, bool)
    channel_mode_changed = Signal(str, str)
    colormap_changed = Signal(str, str)
    processing_params_changed = Signal(str, dict)

    def __init__(self, timeline_type: str, parent=None):
        super().__init__(parent)
        self.timeline_type = timeline_type
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        self.show_checkbox = QCheckBox()
        self.show_checkbox.setChecked(True)
        layout.addWidget(self.show_checkbox)

        channel_layout = QHBoxLayout()
        self.channel_label = QLabel()
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("", "mono")
        self.channel_combo.addItem("", "stereo")
        self.channel_combo.addItem("", "left")
        self.channel_combo.addItem("", "right")
        self.channel_combo.setCurrentIndex(1)
        self.channel_combo.setEnabled(False)
        channel_layout.addWidget(self.channel_label)
        channel_layout.addWidget(self.channel_combo)
        layout.addLayout(channel_layout)

        colormap_layout = QHBoxLayout()
        self.colormap_label = QLabel()
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(["Viridis", "Magma", "Inferno", "Plasma"])
        self.colormap_combo.setCurrentIndex(2)
        self.colormap_combo.setEnabled(False)
        colormap_layout.addWidget(self.colormap_label)
        colormap_layout.addWidget(self.colormap_combo)
        layout.addLayout(colormap_layout)

        self.freq_group = QGroupBox()
        freq_layout = QVBoxLayout(self.freq_group)

        min_freq_layout = QHBoxLayout()
        self.min_freq_label = QLabel()
        self.min_freq_spin = QSpinBox()
        self.min_freq_spin.setRange(20, 20000)
        self.min_freq_spin.setValue(20)
        self.min_freq_spin.setSingleStep(100)
        self.min_freq_spin.setEnabled(False)
        min_freq_layout.addWidget(self.min_freq_label)
        min_freq_layout.addWidget(self.min_freq_spin)
        freq_layout.addLayout(min_freq_layout)

        max_freq_layout = QHBoxLayout()
        self.max_freq_label = QLabel()
        self.max_freq_spin = QSpinBox()
        self.max_freq_spin.setRange(20, 20000)
        self.max_freq_spin.setValue(8000)
        self.max_freq_spin.setSingleStep(100)
        self.max_freq_spin.setEnabled(False)
        max_freq_layout.addWidget(self.max_freq_label)
        max_freq_layout.addWidget(self.max_freq_spin)
        freq_layout.addLayout(max_freq_layout)

        self.apply_params_btn = QPushButton()
        self.apply_params_btn.setEnabled(False)
        freq_layout.addWidget(self.apply_params_btn)

        layout.addWidget(self.freq_group)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.apply_translations()

    def _connect_signals(self):
        self.show_checkbox.toggled.connect(self._on_visibility_changed)
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        self.colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
        self.apply_params_btn.clicked.connect(self._on_apply_params)

    def _on_visibility_changed(self, checked: bool):
        self.channel_combo.setEnabled(checked)
        self.colormap_combo.setEnabled(checked)
        self.min_freq_spin.setEnabled(checked)
        self.max_freq_spin.setEnabled(checked)
        self.apply_params_btn.setEnabled(checked)
        self.visibility_changed.emit(self.timeline_type, checked)

    def _on_channel_changed(self, _: str):
        mode = self.channel_combo.currentData() or "stereo"
        self.channel_mode_changed.emit(self.timeline_type, mode)

    def _on_colormap_changed(self, text: str):
        self.colormap_changed.emit(self.timeline_type, text.lower())

    def _on_apply_params(self):
        fmin = self.min_freq_spin.value()
        fmax = self.max_freq_spin.value()
        if fmin >= fmax:
            fmax = fmin + 100
            self.max_freq_spin.setValue(fmax)
        self.processing_params_changed.emit(
            self.timeline_type,
            {"fmin": float(fmin), "fmax": float(fmax)},
        )

    def set_audio_loaded(self, loaded: bool, info: str = ""):
        if loaded:
            self.status_label.setText(info if info else tr("audio_controls.loaded"))
            self.status_label.setStyleSheet("color: green; font-size: 9pt;")
            self.show_checkbox.setEnabled(True)
            if self.show_checkbox.isChecked():
                self.channel_combo.setEnabled(True)
                self.colormap_combo.setEnabled(True)
                self.min_freq_spin.setEnabled(True)
                self.max_freq_spin.setEnabled(True)
                self.apply_params_btn.setEnabled(True)
        else:
            self.status_label.setText(tr("audio_controls.not_loaded"))
            self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
            self.show_checkbox.setEnabled(False)
            self.show_checkbox.setChecked(False)
            self.channel_combo.setEnabled(False)
            self.colormap_combo.setEnabled(False)
            self.min_freq_spin.setEnabled(False)
            self.max_freq_spin.setEnabled(False)
            self.apply_params_btn.setEnabled(False)

    def set_error(self, error_message: str):
        self.status_label.setText(tr("audio_controls.error", message=error_message))
        self.status_label.setStyleSheet("color: red; font-size: 9pt;")
        self.show_checkbox.setEnabled(False)
        self.show_checkbox.setChecked(False)
        self.channel_combo.setEnabled(False)
        self.colormap_combo.setEnabled(False)
        self.min_freq_spin.setEnabled(False)
        self.max_freq_spin.setEnabled(False)
        self.apply_params_btn.setEnabled(False)

    def set_progress(self, stage: str, percentage: int):
        pass

    def clear_progress(self):
        pass

    def apply_translations(self):
        self.show_checkbox.setText(tr("audio_controls.show_audio_track"))
        self.channel_label.setText(tr("audio_controls.channel"))
        self.channel_combo.setItemText(0, tr("audio.mode.mono"))
        self.channel_combo.setItemText(1, tr("audio.mode.stereo"))
        self.channel_combo.setItemText(2, tr("audio.mode.left"))
        self.channel_combo.setItemText(3, tr("audio.mode.right"))
        self.colormap_label.setText(tr("audio_controls.colormap"))
        self.freq_group.setTitle(tr("audio_controls.frequency_range"))
        self.min_freq_label.setText(tr("audio_controls.min"))
        self.max_freq_label.setText(tr("audio_controls.max"))
        self.apply_params_btn.setText(tr("audio_controls.apply_reprocess"))
        if "green" not in self.status_label.styleSheet():
            self.status_label.setText(tr("audio_controls.not_loaded"))
