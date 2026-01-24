from PySide6.QtCore import QObject, Slot


class DeviceOutputWorker(QObject):
    """Worker thread for non-blocking device output."""

    def __init__(self, serial_device, keyboard_device, data_manager, build_serial_packet_func, get_rgb_func):
        super().__init__()
        self.serial_device = serial_device
        self.keyboard_device = keyboard_device
        self.data_manager = data_manager
        self.build_serial_packet = build_serial_packet_func
        self.get_rgb = get_rgb_func

    @Slot(int, object)
    def send_to_devices(self, position_ms, data_manager=None):
        """Send frame data to devices (runs in worker thread)."""
        # Use provided data manager or fallback to the default one
        dm = data_manager if data_manager is not None else self.data_manager

        # Serial device
        if self.serial_device.is_connected():
            offset_time = position_ms + self.serial_device.offset_ms
            frame_index = dm.get_frame_index_at_ms(offset_time)
            if frame_index is not None and frame_index != self.serial_device.last_sent_frame_index:
                frame = dm.get_frame_at_ms(offset_time)
                if frame is not None:
                    packet = self.build_serial_packet(frame)
                    if self.serial_device.send_data(packet):
                        self.serial_device.last_sent_frame_index = frame_index

        # Keyboard device
        if self.keyboard_device.is_connected():
            offset_time = position_ms + self.keyboard_device.offset_ms
            frame_index = dm.get_frame_index_at_ms(offset_time)
            if frame_index is not None and frame_index != self.keyboard_device.last_sent_frame_index:
                frame = dm.get_frame_at_ms(offset_time)
                if frame is not None:
                    r, g, b = self.get_rgb(frame)
                    if self.keyboard_device.send_frame(r, g, b):
                        self.keyboard_device.last_sent_frame_index = frame_index
