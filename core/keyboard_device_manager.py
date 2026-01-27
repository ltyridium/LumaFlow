import requests
import base64
import uuid
from PySide6.QtCore import QObject, Signal


class KeyboardDeviceManager(QObject):
    """
    Keyboard / Light control manager for NEW gRPC-Web driver.
    Uses /iot_manager.IotManager/ControlDeviceLight
    (No raw HID packets anymore)
    """

    connection_changed = Signal(bool, str)
    frame_sent = Signal(int)

    URL = "http://127.0.0.1:6015/iot_manager.IotManager/ControlDeviceLight"

    DEFAULT_DEVICE_PATH = (
        r"\\?\HID#VID_3151&PID_504E&MI_02"
        r"#8&ca262e&0&0000"
        r"#{4d1e55b2-f16f-11cf-88cb-001111000030}"
    )

    # ---- Light action enum (from reverse engineering) ----
    ACTION_SET_LIGHT = 2

    def __init__(self):
        super().__init__()
        self.device_path = self.DEFAULT_DEVICE_PATH
        self.is_initialized = False
        self.frames_sent = 0

        # Cached last color (dedup)
        self.last_rgb = None

        # UI settings (not used by gRPC implementation yet)
        self.target_keyboard = False
        self.target_lightstrip = True
        self.selected_channel = 0  # 0 for first channel
        self.offset_ms = 0

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _grpc_web_wrap(self, proto_bytes: bytes) -> str:
        """
        gRPC-Web-Text framing:
        1 byte compressed flag (0)
        4 bytes message length (big endian)
        + protobuf payload
        then base64
        """
        header = b"\x00" + len(proto_bytes).to_bytes(4, "big")
        return base64.b64encode(header + proto_bytes).decode()

    def _post(self, proto_bytes: bytes) -> bool:
        headers = {
            "Content-Type": "application/grpc-web-text",
            "Accept": "application/grpc-web-text",
            "x-grpc-web": "1",
        }

        try:
            res = requests.post(
                self.URL,
                data=self._grpc_web_wrap(proto_bytes),
                headers=headers,
                timeout=0.5,
            )
            return res.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Protobuf builders (reverse engineered)
    # ------------------------------------------------------------------

    def _build_request(
        self,
        action: int,
        rgb: tuple | None = None,
    ) -> bytes:
        """
        Build ControlDeviceLight protobuf.

        message ControlDeviceLightRequest {
          string device_path = 1;
          LightAction action = 2;
          RGB rgb = 3;          // optional (future / partially confirmed)
          string request_id = 4;
        }
        """

        buf = bytearray()

        # field 1: device_path (string)
        path_bytes = self.device_path.encode("utf-8")
        buf += b"\x0a" + bytes([len(path_bytes)]) + path_bytes

        # field 2: action enum
        buf += b"\x10" + bytes([action])

        # field 3: RGB (optional, safe even if driver ignores it)
        if rgb is not None:
            r, g, b = rgb
            # packed message: field 3 (0x1a), length 3
            buf += b"\x1a\x03" + bytes([r & 0xFF, g & 0xFF, b & 0xFF])

        # field 4: request_id (UUID string)
        req_id = str(uuid.uuid4()).encode("utf-8")
        buf += b"\x22" + bytes([len(req_id)]) + req_id

        return bytes(buf)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Initialize / wake up lighting control.
        """
        proto = self._build_request(action=self.ACTION_SET_LIGHT)

        if self._post(proto):
            self.is_initialized = True
            self.frames_sent = 0
            self.connection_changed.emit(True, "Device connected")
            return True

        self.connection_changed.emit(False, "Connection failed")
        return False

    def disconnect(self):
        self.is_initialized = False
        self.frames_sent = 0
        self.connection_changed.emit(False, "Disconnected")

    def is_connected(self) -> bool:
        return self.is_initialized

    def send_color(self, r: int, g: int, b: int) -> bool:
        """
        Set light color using new ControlDeviceLight API.
        """
        if not self.is_initialized:
            return False

        rgb = (r, g, b)

        # Dedup
        if rgb == self.last_rgb:
            return True

        proto = self._build_request(
            action=self.ACTION_SET_LIGHT,
            rgb=rgb,
        )

        if self._post(proto):
            self.last_rgb = rgb
            self.frames_sent += 1
            self.frame_sent.emit(self.frames_sent)
            return True

        return False

    def reset_stats(self):
        self.frames_sent = 0
        self.last_rgb = None
        self.frame_sent.emit(0)

    def reset_frame_tracking(self):
        """Reset frame tracking for new playback session."""
        self.reset_stats()

    # ------------------------------------------------------------------
    # Setter methods for UI configuration
    # ------------------------------------------------------------------

    def set_device_path(self, path):
        """Set the HID device path."""
        self.device_path = path

    def set_target_keyboard(self, enabled):
        """Enable/disable sending to keyboard."""
        self.target_keyboard = enabled

    def set_target_lightstrip(self, enabled):
        """Enable/disable sending to light strip."""
        self.target_lightstrip = enabled

    def set_selected_channel(self, channel):
        """Set which channel's RGB to use (-1 for average)."""
        self.selected_channel = channel

    def set_offset(self, offset_ms):
        """Set timing offset in milliseconds."""
        self.offset_ms = offset_ms
