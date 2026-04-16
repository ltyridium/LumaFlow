from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QComboBox, QLabel, QSpinBox, QLineEdit
)
from PySide6.QtCore import Signal


class SerialDevicePanel(QGroupBox):
    """Panel for Serial RF Transmitter controls."""
    connect_requested = Signal(str, int)  # port, baud_rate
    disconnect_requested = Signal()
    offset_changed = Signal(int)
    refresh_requested = Signal()
    auth_lic_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Serial RF Transmitter", parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self._default_offset = 200

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
        self.offset_spin.setValue(self._default_offset)
        self.offset_spin.setMinimumWidth(80)
        offset_row.addWidget(self.offset_spin)
        self.offset_minus_50_btn = QPushButton("-50")
        offset_row.addWidget(self.offset_minus_50_btn)
        self.offset_minus_10_btn = QPushButton("-10")
        offset_row.addWidget(self.offset_minus_10_btn)
        self.offset_plus_10_btn = QPushButton("+10")
        offset_row.addWidget(self.offset_plus_10_btn)
        self.offset_plus_50_btn = QPushButton("+50")
        offset_row.addWidget(self.offset_plus_50_btn)
        self.reset_offset_btn = QPushButton("Reset")
        offset_row.addWidget(self.reset_offset_btn)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("AUTH LIC:"))
        self.auth_lic_edit = QLineEdit()
        self.auth_lic_edit.setClearButtonEnabled(True)
        auth_row.addWidget(self.auth_lic_edit)
        layout.addLayout(auth_row)

        auth_status_row = QHBoxLayout()
        auth_status_row.addWidget(QLabel("Auth Status:"))
        self.auth_status_label = QLabel("Not Sent")
        auth_status_row.addWidget(self.auth_status_label)
        auth_status_row.addStretch()
        layout.addLayout(auth_status_row)

        lic_info_box = QGroupBox("LIC Info")
        lic_info_layout = QVBoxLayout(lic_info_box)

        self.lic_device_label = QLabel("Device: --")
        lic_info_layout.addWidget(self.lic_device_label)
        self.lic_expire_label = QLabel("Expire At: --")
        lic_info_layout.addWidget(self.lic_expire_label)
        self.lic_validity_label = QLabel("Validity: --")
        lic_info_layout.addWidget(self.lic_validity_label)
        self.lic_signature_label = QLabel("Signature: --")
        lic_info_layout.addWidget(self.lic_signature_label)
        self.lic_parse_status_label = QLabel("Status: No LIC loaded")
        self.lic_parse_status_label.setWordWrap(True)
        lic_info_layout.addWidget(self.lic_parse_status_label)
        layout.addWidget(lic_info_box)

        # Frames sent counter
        self.frames_label = QLabel("Frames Sent: 0")
        layout.addWidget(self.frames_label)

        # Connect signals
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        self.offset_spin.valueChanged.connect(self.offset_changed.emit)
        self.offset_minus_50_btn.clicked.connect(lambda: self._adjust_offset(-50))
        self.offset_minus_10_btn.clicked.connect(lambda: self._adjust_offset(-10))
        self.offset_plus_10_btn.clicked.connect(lambda: self._adjust_offset(10))
        self.offset_plus_50_btn.clicked.connect(lambda: self._adjust_offset(50))
        self.reset_offset_btn.clicked.connect(lambda: self.offset_spin.setValue(self._default_offset))
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.auth_lic_edit.textChanged.connect(self.auth_lic_changed.emit)

    def set_default_offset(self, value: int):
        self._default_offset = int(value)

    def _adjust_offset(self, delta: int):
        self.offset_spin.setValue(self.offset_spin.value() + int(delta))

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

    def set_auth_lic(self, value):
        self.auth_lic_edit.setText(value)

    def set_auth_status(self, status):
        self.auth_status_label.setText(status)

    def set_lic_info(self, info):
        self.lic_device_label.setText(f"Device: {info.get('device_mac', '--')}")
        self.lic_expire_label.setText(f"Expire At: {info.get('expire_at', '--')}")
        self.lic_validity_label.setText(f"Validity: {info.get('validity', '--')}")
        self.lic_signature_label.setText(f"Signature: {info.get('signature', '--')}")
        self.lic_parse_status_label.setText(f"Status: {info.get('status', 'No LIC loaded')}")

        validity_color = "#ff4d4f" if info.get("is_expired") else "#d9d9d9"
        if info.get("valid") and not info.get("is_expired"):
            validity_color = "#52c41a"
        if not info.get("valid") and not info.get("empty"):
            validity_color = "#ff4d4f"

        status_color = "#d9d9d9"
        if info.get("valid"):
            status_color = "#52c41a"
        elif not info.get("empty"):
            status_color = "#ff4d4f"

        self.lic_validity_label.setStyleSheet(f"color: {validity_color};")
        self.lic_parse_status_label.setStyleSheet(f"color: {status_color};")


class DeviceOutputWidget(QWidget):
    """Main widget containing the serial output panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.serial_panel = SerialDevicePanel()

        layout.addWidget(self.serial_panel)
        layout.addStretch()
