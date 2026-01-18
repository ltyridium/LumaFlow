from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QComboBox, QLabel, QSpinBox, QLineEdit, QCheckBox
)
from PySide6.QtCore import Signal


class SerialDevicePanel(QGroupBox):
    """Panel for Serial RF Transmitter controls."""
    connect_requested = Signal(str, int)  # port, baud_rate
    disconnect_requested = Signal()
    offset_changed = Signal(int)
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Serial RF Transmitter", parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Port selection row
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)
        port_row.addWidget(self.port_combo)
        self.refresh_btn = QPushButton("Refresh")
        port_row.addWidget(self.refresh_btn)
        port_row.addStretch()
        layout.addLayout(port_row)

        # Baud rate row
        baud_row = QHBoxLayout()
        baud_row.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "230400", "512000", "460800", "921600"])
        self.baud_combo.setCurrentText("512000")
        baud_row.addWidget(self.baud_combo)
        baud_row.addStretch()
        layout.addLayout(baud_row)

        # Connect button and status
        connect_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        connect_row.addWidget(self.connect_btn)
        self.status_label = QLabel("Disconnected")
        connect_row.addWidget(self.status_label)
        connect_row.addStretch()
        layout.addLayout(connect_row)

        # Offset control
        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("Offset (ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-1000, 1000)
        self.offset_spin.setValue(170)  # Default offset for serial devices
        self.offset_spin.setMinimumWidth(80)
        offset_row.addWidget(self.offset_spin)
        self.reset_offset_btn = QPushButton("Reset")
        offset_row.addWidget(self.reset_offset_btn)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        # Frames sent counter
        self.frames_label = QLabel("Frames Sent: 0")
        layout.addWidget(self.frames_label)

        # Connect signals
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        self.offset_spin.valueChanged.connect(self.offset_changed.emit)
        self.reset_offset_btn.clicked.connect(lambda: self.offset_spin.setValue(0))
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)

    def _on_connect_clicked(self):
        if self.connect_btn.text() == "Connect":
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            self.connect_requested.emit(port, baud)
        else:
            self.disconnect_requested.emit()

    def update_ports(self, ports):
        """Update the list of available ports."""
        current = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)

    def set_connected(self, connected):
        """Update UI to reflect connection state."""
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.status_label.setText("Connected" if connected else "Disconnected")

    def update_frames_sent(self, count):
        """Update the frames sent counter."""
        self.frames_label.setText(f"Frames Sent: {count}")


class KeyboardDevicePanel(QGroupBox):
    """Panel for Keyboard/LightStrip HID device controls."""
    connect_requested = Signal()
    disconnect_requested = Signal()
    offset_changed = Signal(int)
    target_keyboard_changed = Signal(bool)
    target_lightstrip_changed = Signal(bool)
    channel_changed = Signal(int)
    device_path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Keyboard/LightStrip (HID)", parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Device path
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Device:"))
        self.device_path_edit = QLineEdit()
        self.device_path_edit.setPlaceholderText("HID Device Path")
        path_row.addWidget(self.device_path_edit)
        layout.addLayout(path_row)

        # Target type selection with checkboxes (multi-select)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target:"))
        self.keyboard_checkbox = QCheckBox("Keyboard")
        self.keyboard_checkbox.setChecked(False)
        target_row.addWidget(self.keyboard_checkbox)
        self.lightstrip_checkbox = QCheckBox("LightStrip")
        self.lightstrip_checkbox.setChecked(True)  # Default enabled
        target_row.addWidget(self.lightstrip_checkbox)
        target_row.addStretch()
        layout.addLayout(target_row)

        # Channel selection
        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("Average (All)", -1)
        for i in range(10):
            self.channel_combo.addItem(f"CH {i}", i)
        self.channel_combo.setCurrentIndex(0)  # Default to average
        channel_row.addWidget(self.channel_combo)
        channel_row.addStretch()
        layout.addLayout(channel_row)

        # Connect button and status
        connect_row = QHBoxLayout()
        self.connect_btn = QPushButton("Initialize")
        connect_row.addWidget(self.connect_btn)
        self.status_label = QLabel("Not Initialized")
        connect_row.addWidget(self.status_label)
        connect_row.addStretch()
        layout.addLayout(connect_row)

        # Offset control
        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("Offset (ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-1000, 1000)
        self.offset_spin.setValue(50)
        self.offset_spin.setMinimumWidth(80)
        offset_row.addWidget(self.offset_spin)
        self.reset_offset_btn = QPushButton("Reset")
        offset_row.addWidget(self.reset_offset_btn)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        # Frames sent counter
        self.frames_label = QLabel("Frames Sent: 0")
        layout.addWidget(self.frames_label)

        # Connect signals
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        self.offset_spin.valueChanged.connect(self.offset_changed.emit)
        self.reset_offset_btn.clicked.connect(lambda: self.offset_spin.setValue(0))
        self.keyboard_checkbox.toggled.connect(self.target_keyboard_changed.emit)
        self.lightstrip_checkbox.toggled.connect(self.target_lightstrip_changed.emit)
        self.channel_combo.currentIndexChanged.connect(
            lambda: self.channel_changed.emit(self.channel_combo.currentData())
        )
        self.device_path_edit.textChanged.connect(self.device_path_changed.emit)

    def _on_connect_clicked(self):
        if self.connect_btn.text() == "Initialize":
            self.connect_requested.emit()
        else:
            self.disconnect_requested.emit()

    def set_connected(self, connected):
        """Update UI to reflect connection state."""
        self.connect_btn.setText("Disconnect" if connected else "Initialize")
        self.status_label.setText("Initialized" if connected else "Not Initialized")

    def update_frames_sent(self, count):
        """Update the frames sent counter."""
        self.frames_label.setText(f"Frames Sent: {count}")

    def set_device_path(self, path):
        """Set the device path in the text field."""
        self.device_path_edit.setText(path)


class DeviceOutputWidget(QWidget):
    """Main widget containing both device panels."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.serial_panel = SerialDevicePanel()
        self.keyboard_panel = KeyboardDevicePanel()

        layout.addWidget(self.serial_panel)
        layout.addWidget(self.keyboard_panel)
        layout.addStretch()
