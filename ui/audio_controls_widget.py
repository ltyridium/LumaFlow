from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
                               QComboBox, QSlider, QLabel, QGroupBox, QProgressBar,
                               QSpinBox, QPushButton)
from PySide6.QtCore import Signal, Qt


class AudioControlsWidget(QWidget):
    """User controls for audio visualization settings"""

    # Signals
    visibility_changed = Signal(str, bool)  # timeline_type, visible
    channel_mode_changed = Signal(str, str)  # timeline_type, mode
    colormap_changed = Signal(str, str)     # timeline_type, colormap
    processing_params_changed = Signal(str, dict)  # timeline_type, params (fmin, fmax)

    def __init__(self, timeline_type: str, parent=None):
        super().__init__(parent)
        self.timeline_type = timeline_type
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # Show/Hide checkbox
        self.show_checkbox = QCheckBox("显示音频轨道")
        self.show_checkbox.setChecked(True)
        layout.addWidget(self.show_checkbox)

        # Channel selection
        channel_layout = QHBoxLayout()
        channel_label = QLabel("声道:")
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["单声道", "立体声", "左声道", "右声道"])
        self.channel_combo.setCurrentIndex(1)  # 默认选择"立体声"
        self.channel_combo.setEnabled(False)
        channel_layout.addWidget(channel_label)
        channel_layout.addWidget(self.channel_combo)
        layout.addLayout(channel_layout)

        # Colormap selection
        colormap_layout = QHBoxLayout()
        colormap_label = QLabel("色彩映射:")
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(["Viridis", "Magma", "Inferno", "Plasma"])
        self.colormap_combo.setCurrentIndex(2)  # 默认选择"Inferno"
        self.colormap_combo.setEnabled(False)
        colormap_layout.addWidget(colormap_label)
        colormap_layout.addWidget(self.colormap_combo)
        layout.addLayout(colormap_layout)

        # Frequency range settings
        freq_group = QGroupBox("频率范围 (Hz)")
        freq_layout = QVBoxLayout(freq_group)

        # Min Freq
        min_freq_layout = QHBoxLayout()
        min_freq_label = QLabel("最小:")
        self.min_freq_spin = QSpinBox()
        self.min_freq_spin.setRange(20, 20000)
        self.min_freq_spin.setValue(20)
        self.min_freq_spin.setSingleStep(100)
        self.min_freq_spin.setEnabled(False)
        min_freq_layout.addWidget(min_freq_label)
        min_freq_layout.addWidget(self.min_freq_spin)
        freq_layout.addLayout(min_freq_layout)

        # Max Freq
        max_freq_layout = QHBoxLayout()
        max_freq_label = QLabel("最大:")
        self.max_freq_spin = QSpinBox()
        self.max_freq_spin.setRange(20, 20000)
        self.max_freq_spin.setValue(8000)
        self.max_freq_spin.setSingleStep(100)
        self.max_freq_spin.setEnabled(False)
        max_freq_layout.addWidget(max_freq_label)
        max_freq_layout.addWidget(self.max_freq_spin)
        freq_layout.addLayout(max_freq_layout)

        # Apply button
        self.apply_params_btn = QPushButton("应用更改 (重新处理)")
        self.apply_params_btn.setEnabled(False)
        freq_layout.addWidget(self.apply_params_btn)

        layout.addWidget(freq_group)

        # Status label
        self.status_label = QLabel("未加载音频")
        self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _connect_signals(self):
        """Connect internal signals"""
        self.show_checkbox.toggled.connect(self._on_visibility_changed)
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        self.colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
        self.apply_params_btn.clicked.connect(self._on_apply_params)

    def _on_visibility_changed(self, checked: bool):
        """Handle visibility checkbox toggle"""
        # Enable/disable controls based on visibility
        self.channel_combo.setEnabled(checked)
        self.colormap_combo.setEnabled(checked)
        self.min_freq_spin.setEnabled(checked)
        self.max_freq_spin.setEnabled(checked)
        self.apply_params_btn.setEnabled(checked)

        self.visibility_changed.emit(self.timeline_type, checked)

    def _on_channel_changed(self, text: str):
        """Handle channel selection change"""
        # Map Chinese text to English mode
        mode_map = {
            "单声道": "mono",
            "立体声": "stereo",
            "左声道": "left",
            "右声道": "right"
        }
        mode = mode_map.get(text, "stereo")
        self.channel_mode_changed.emit(self.timeline_type, mode)

    def _on_colormap_changed(self, text: str):
        """Handle colormap selection change"""
        colormap = text.lower()
        self.colormap_changed.emit(self.timeline_type, colormap)

    def _on_apply_params(self):
        """Handle processing parameters application"""
        fmin = self.min_freq_spin.value()
        fmax = self.max_freq_spin.value()

        if fmin >= fmax:
            # Simple validation
            fmax = fmin + 100
            self.max_freq_spin.setValue(fmax)

        params = {
            'fmin': float(fmin),
            'fmax': float(fmax)
        }
        self.processing_params_changed.emit(self.timeline_type, params)

    def set_audio_loaded(self, loaded: bool, info: str = ""):
        """Update status when audio is loaded or unloaded"""
        if loaded:
            self.status_label.setText(info if info else "音频已加载")
            self.status_label.setStyleSheet("color: green; font-size: 9pt;")
            self.show_checkbox.setEnabled(True)
            # 只有在已显示的情况下才启用控件
            if self.show_checkbox.isChecked():
                self.channel_combo.setEnabled(True)
                self.colormap_combo.setEnabled(True)
                self.min_freq_spin.setEnabled(True)
                self.max_freq_spin.setEnabled(True)
                self.apply_params_btn.setEnabled(True)
        else:
            self.status_label.setText("未加载音频")
            self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
            self.show_checkbox.setEnabled(False)
            self.show_checkbox.setChecked(False)
            # Disable all controls
            self.channel_combo.setEnabled(False)
            self.colormap_combo.setEnabled(False)
            self.min_freq_spin.setEnabled(False)
            self.max_freq_spin.setEnabled(False)
            self.apply_params_btn.setEnabled(False)

    def set_error(self, error_message: str):
        """Display error message"""
        self.status_label.setText(f"错误: {error_message}")
        self.status_label.setStyleSheet("color: red; font-size: 9pt;")
        self.show_checkbox.setEnabled(False)
        self.show_checkbox.setChecked(False)
        # Disable all controls
        self.channel_combo.setEnabled(False)
        self.colormap_combo.setEnabled(False)
        self.min_freq_spin.setEnabled(False)
        self.max_freq_spin.setEnabled(False)
        self.apply_params_btn.setEnabled(False)

    def set_progress(self, stage: str, percentage: int):
        """Update progress bar and status - now handled by main window"""
        pass

    def clear_progress(self):
        """Hide progress bar - now handled by main window"""
        pass
