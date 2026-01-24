from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTabWidget, QWidget)
from PySide6.QtCore import Qt


class AudioSettingsDialog(QDialog):
    """Separate dialog window for audio visualization settings"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("音频可视化设置")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Create tab widget for source and edit timelines
        tab_widget = QTabWidget()

        # Source timeline tab
        source_tab = QWidget()
        source_layout = QVBoxLayout(source_tab)
        # Show the widget and add to layout
        self.main_window.source_audio_controls.show()
        source_layout.addWidget(self.main_window.source_audio_controls)
        source_layout.addStretch()
        tab_widget.addTab(source_tab, "源时间轴")

        # Edit timeline tab
        edit_tab = QWidget()
        edit_layout = QVBoxLayout(edit_tab)
        # Show the widget and add to layout
        self.main_window.edit_audio_controls.show()
        edit_layout.addWidget(self.main_window.edit_audio_controls)
        edit_layout.addStretch()
        tab_widget.addTab(edit_tab, "编辑时间轴")

        layout.addWidget(tab_widget)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def done(self, result):
        # Don't reparent, just hide the widgets when dialog closes
        # Keep them in the dialog's layout but make dialog invisible
        super().done(result)
