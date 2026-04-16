from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QWidget

from core.i18n import tr


class AudioSettingsDialog(QDialog):
    """Separate dialog window for audio visualization settings."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self._init_ui()
        self.apply_translations()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()

        source_tab = QWidget()
        source_layout = QVBoxLayout(source_tab)
        self.main_window.source_audio_controls.show()
        source_layout.addWidget(self.main_window.source_audio_controls)
        source_layout.addStretch()
        self.tab_widget.addTab(source_tab, "")

        edit_tab = QWidget()
        edit_layout = QVBoxLayout(edit_tab)
        self.main_window.edit_audio_controls.show()
        edit_layout.addWidget(self.main_window.edit_audio_controls)
        edit_layout.addStretch()
        self.tab_widget.addTab(edit_tab, "")

        layout.addWidget(self.tab_widget)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    def apply_translations(self):
        self.setWindowTitle(tr("audio_settings.title"))
        self.tab_widget.setTabText(0, tr("audio_settings.source_tab"))
        self.tab_widget.setTabText(1, tr("audio_settings.edit_tab"))
        self.close_button.setText(tr("audio_settings.close"))

    def done(self, result):
        super().done(result)
