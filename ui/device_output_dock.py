from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QComboBox, QLabel, QSpinBox, QLineEdit
)
from PySide6.QtCore import Signal
from core.i18n import tr


class SerialDevicePanel(QGroupBox):
    """Panel for Serial RF Transmitter controls."""
    connect_requested = Signal(str, int)  # port, baud_rate
    disconnect_requested = Signal()
    offset_changed = Signal(int)
    refresh_requested = Signal()
    auth_lic_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self._default_offset = 200

        # Port selection row
        port_row = QHBoxLayout()
        self.port_label = QLabel()
        port_row.addWidget(self.port_label)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)
        port_row.addWidget(self.port_combo)
        self.refresh_btn = QPushButton()
        port_row.addWidget(self.refresh_btn)
        port_row.addStretch()
        layout.addLayout(port_row)

        # Baud rate row
        baud_row = QHBoxLayout()
        self.baud_label = QLabel()
        baud_row.addWidget(self.baud_label)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "230400", "512000", "460800", "921600"])
        self.baud_combo.setCurrentText("512000")
        baud_row.addWidget(self.baud_combo)
        baud_row.addStretch()
        layout.addLayout(baud_row)

        # Connect button and status
        connect_row = QHBoxLayout()
        self.connect_btn = QPushButton()
        connect_row.addWidget(self.connect_btn)
        self.status_label = QLabel()
        connect_row.addWidget(self.status_label)
        connect_row.addStretch()
        layout.addLayout(connect_row)

        # Offset control
        offset_row = QHBoxLayout()
        self.offset_label = QLabel()
        offset_row.addWidget(self.offset_label)
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
        self.reset_offset_btn = QPushButton()
        offset_row.addWidget(self.reset_offset_btn)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        auth_row = QHBoxLayout()
        self.auth_lic_label = QLabel()
        auth_row.addWidget(self.auth_lic_label)
        self.auth_lic_edit = QLineEdit()
        self.auth_lic_edit.setClearButtonEnabled(True)
        auth_row.addWidget(self.auth_lic_edit)
        layout.addLayout(auth_row)

        auth_status_row = QHBoxLayout()
        self.auth_status_title_label = QLabel()
        auth_status_row.addWidget(self.auth_status_title_label)
        self.auth_status_label = QLabel()
        auth_status_row.addWidget(self.auth_status_label)
        auth_status_row.addStretch()
        layout.addLayout(auth_status_row)

        self.lic_info_box = QGroupBox()
        lic_info_box = self.lic_info_box
        lic_info_layout = QVBoxLayout(lic_info_box)

        self.lic_device_label = QLabel()
        lic_info_layout.addWidget(self.lic_device_label)
        self.lic_expire_label = QLabel()
        lic_info_layout.addWidget(self.lic_expire_label)
        self.lic_validity_label = QLabel()
        lic_info_layout.addWidget(self.lic_validity_label)
        self.lic_signature_label = QLabel()
        lic_info_layout.addWidget(self.lic_signature_label)
        self.lic_parse_status_label = QLabel()
        self.lic_parse_status_label.setWordWrap(True)
        lic_info_layout.addWidget(self.lic_parse_status_label)
        layout.addWidget(lic_info_box)

        # Frames sent counter
        self.frames_label = QLabel()
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
        self.apply_translations()

    def set_default_offset(self, value: int):
        self._default_offset = int(value)

    def _adjust_offset(self, delta: int):
        self.offset_spin.setValue(self.offset_spin.value() + int(delta))

    def _on_connect_clicked(self):
        if self.connect_btn.text() == tr("device_output.connect"):
            port = self.port_combo.currentData()
            baud = int(self.baud_combo.currentText())
            self.connect_requested.emit(port, baud)
        else:
            self.disconnect_requested.emit()

    def update_ports(self, ports):
        """Update the list of available ports."""
        current = self.port_combo.currentData()
        self.port_combo.clear()
        for port_info in ports:
            device = port_info['device']
            description = port_info['description']
            # Display format: "COM6 - Device Name"
            display_text = f"{device} - {description}"
            self.port_combo.addItem(display_text, device)
        if current:
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def set_connected(self, connected):
        """Update UI to reflect connection state."""
        self.connect_btn.setText(tr("device_output.disconnect") if connected else tr("device_output.connect"))
        self.status_label.setText(tr("device_output.connected") if connected else tr("device_output.disconnected"))

    def update_frames_sent(self, count):
        """Update the frames sent counter."""
        self.frames_label.setText(tr("device_output.frames_sent", count=count))

    def set_auth_lic(self, value):
        self.auth_lic_edit.setText(value)

    def set_auth_status(self, status):
        status_key = {
            "Not Sent": "device_output.auth_not_sent",
            "Sent": "device_output.auth_sent",
            "Config Error": "device_output.auth_config_error",
            "Send Failed": "device_output.auth_send_failed",
        }.get(status)
        self.auth_status_label.setText(tr(status_key) if status_key else status)

    def set_lic_info(self, info):
        self.lic_device_label.setText(tr("device_output.lic_device", value=info.get("device_mac", "--")))
        self.lic_expire_label.setText(tr("device_output.lic_expire_at", value=info.get("expire_at", "--")))
        self.lic_validity_label.setText(tr("device_output.lic_validity", value=info.get("validity", "--")))
        self.lic_signature_label.setText(tr("device_output.lic_signature", value=info.get("signature", "--")))
        self.lic_parse_status_label.setText(
            tr("device_output.lic_status", value=info.get("status", tr("device_output.lic_status_empty")))
        )

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

    def apply_translations(self):
        self.setTitle(tr("device_output.group_title"))
        self.port_label.setText(tr("device_output.port"))
        self.refresh_btn.setText(tr("device_output.refresh"))
        self.baud_label.setText(tr("device_output.baud"))
        self.offset_label.setText(tr("device_output.offset"))
        self.reset_offset_btn.setText(tr("device_output.reset"))
        self.auth_lic_label.setText(tr("device_output.auth_lic"))
        self.auth_status_title_label.setText(tr("device_output.auth_status"))
        self.lic_info_box.setTitle(tr("device_output.lic_info"))
        self.set_connected(False)
        self.set_auth_status("Not Sent")
        self.update_frames_sent(0)
        self.set_lic_info({
            "device_mac": "--",
            "expire_at": "--",
            "validity": "--",
            "signature": "--",
            "status": tr("device_output.lic_status_empty"),
            "is_expired": False,
            "valid": False,
            "empty": True,
        })


class DeviceOutputWidget(QWidget):
    """Main widget containing the serial output panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.serial_panel = SerialDevicePanel()

        layout.addWidget(self.serial_panel)
        layout.addStretch()
