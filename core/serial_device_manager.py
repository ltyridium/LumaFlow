import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, Signal


class SerialDeviceManager(QObject):
    """
    Manager for USB Serial RF Transmitter device.
    Handles serial port lifecycle and raw byte transmission.
    """
    connection_changed = Signal(bool, str)  # (connected, message)
    frame_sent = Signal(int)  # frames_sent count

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.frames_sent = 0
        self.last_sent_frame_index = -1  # For deduplication
        self.offset_ms = 0

    def get_ports(self):
        """Get list of available serial ports."""
        return [port.device for port in serial.tools.list_ports.comports()]

    def connect(self, port, baud_rate=512000):
        """Connect to the specified serial port."""
        try:
            self.serial_port = serial.Serial(port, baudrate=baud_rate, timeout=1)
            self.frames_sent = 0
            self.last_sent_frame_index = -1
            self.frame_sent.emit(0)
            return True
        except serial.SerialException as e:
            self.serial_port = None
            self.connection_changed.emit(False, f"Connection failed: {e}")
            return False

    def mark_connected(self, message):
        """Emit a successful connection state after higher-level init succeeds."""
        self.connection_changed.emit(True, message)

    def disconnect(self, message="Disconnected", emit_signal=True):
        """Disconnect from the serial port."""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None
        self.frames_sent = 0
        self.last_sent_frame_index = -1
        self.frame_sent.emit(0)
        if emit_signal:
            self.connection_changed.emit(False, message)

    def is_connected(self):
        """Check if connected to a serial port."""
        return self.serial_port is not None and self.serial_port.is_open

    def send_data(self, data_bytes, count_frame=True):
        """Send raw bytes to the serial port."""
        if self.is_connected():
            try:
                self.serial_port.write(data_bytes)
                if count_frame:
                    self.frames_sent += 1
                    self.frame_sent.emit(self.frames_sent)
                return True
            except serial.SerialException as e:
                print(f"Serial send error: {e}")
                self.disconnect(message=f"Disconnected: {e}")
                return False
        return False

    def set_offset(self, offset_ms):
        """Set the timing offset in milliseconds."""
        self.offset_ms = offset_ms

    def get_offset(self):
        """Get the current timing offset."""
        return self.offset_ms

    def reset_frame_tracking(self):
        """Reset frame tracking for new playback session."""
        self.last_sent_frame_index = -1
        self.frames_sent = 0
        self.frame_sent.emit(0)

    def get_frames_sent(self):
        """Get the number of frames sent."""
        return self.frames_sent
