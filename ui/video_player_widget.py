# file: ui/vlc_video_widget.py

import sys
import os
import time
from urllib.parse import unquote
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QFrame, QStyle, QSizePolicy

try:
    import vlc
    vlc_available = True
except ImportError:
    vlc_available = False

class VideoPlayerWidget(QWidget):
    """A video player widget using the python-vlc library."""

    position_changed_manually = Signal(int)
    position_changed_during_playback = Signal(int)
    playback_started = Signal()  # 新增：播放开始信号
    playback_stopped = Signal()  # 新增：播放停止信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_media_loaded = False
        self._is_scrubbing = False
        self._is_playing = False
        self._auto_pause_on_play = False

        # Master clock variables for smooth playback
        self.current_time_ms = 0
        self.playback_start_time = 0  # perf_counter when playback started
        self.playback_start_offset_ms = 0  # offset in ms when playback started
        self.last_vlc_time_ms = -1  # last read VLC time
        self.vlc_read_counter = 0  # counter for VLC sync (read every 10 ticks = 100ms)

        if not vlc_available:
            self._create_fallback_ui()
            return

        # --- VLC Setup ---
        self.instance = vlc.Instance()
        self.media_player = self.instance.media_player_new()

        # --- UI Elements ---
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("QFrame { background-color: black; }")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Handle resize events for proper video scaling
        self.video_frame.setMinimumSize(400, 300)

        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setEnabled(False)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setEnabled(False)
        self.position_slider.setToolTip("Video position")

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setToolTip("Volume")

        self.file_label = QLabel("No video loaded")
        self.file_label.setWordWrap(True)
        self.file_label.setToolTip("Currently loaded video file")

        # --- Layout ---
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.position_slider)
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Volume:"))
        volume_layout.addWidget(self.volume_slider)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.video_frame)
        main_layout.addWidget(self.file_label)
        main_layout.addLayout(control_layout)
        main_layout.addLayout(volume_layout)

        # --- Connect Signals ---
        self.play_button.clicked.connect(self.play_clicked)
        self.position_slider.sliderPressed.connect(self._slider_pressed)
        self.position_slider.sliderMoved.connect(self._slider_scrubbed)
        self.position_slider.sliderReleased.connect(self._slider_released)
        self.volume_slider.valueChanged.connect(self.change_volume)

        # Connect VLC events
        events = self.media_player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerPositionChanged, self._on_vlc_position_changed)
        events.event_attach(vlc.EventType.MediaPlayerTimeChanged, self._on_vlc_time_changed)
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached)
        events.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_vlc_error)
        events.event_attach(vlc.EventType.MediaPlayerBuffering, self._on_vlc_buffering)
        events.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_vlc_playing)
        events.event_attach(vlc.EventType.MediaPlayerPaused, self._on_vlc_paused)
        events.event_attach(vlc.EventType.MediaParsedChanged, self._on_vlc_media_parsed)

        # Master clock timer (100Hz for smooth playback head updates)
        self.master_clock_timer = QTimer(self)
        self.master_clock_timer.setInterval(10)  # 10ms = 100Hz
        self.master_clock_timer.timeout.connect(self._on_master_tick)


    def _create_fallback_ui(self):
        """Creates a placeholder UI if VLC is not installed."""
        layout = QVBoxLayout(self)
        label = QLabel("VLC not found.\nPlease install VLC Media Player and the 'python-vlc' library.\n\n"
                      "To install:\n"
                      "1. Download VLC from https://www.videolan.org/vlc/\n"
                      "2. Install python-vlc: pip install python-vlc")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("QLabel { color: red; font-weight: bold; }")
        layout.addWidget(label)

    def load_video(self, file_path: str):
        if not vlc_available:
            return

        # Release any existing media
        if self.media_player.get_media():
            self.media_player.stop()

        media = self.instance.media_new(file_path)
        media.parse()
        self.media_player.set_media(media)

        # 保存文件路径供后续使用
        self._current_video_path = file_path

        # Tell VLC where to draw the video
        self._attach_video_to_frame()

        self.file_label.setText(f"Loading: {os.path.basename(file_path)}...")

        # Play and immediately pause to load the first frame and get duration
        # Then immediately pause to ensure video doesn't auto-play after loading
        self._auto_pause_on_play = True

        self.media_player.play()
        self.media_player.pause()

        # Check media loading with a timer instead of singleShot for better reliability
        self._media_load_timer = QTimer()
        self._media_load_timer.timeout.connect(self._check_media_loaded)
        self._media_load_timer.setSingleShot(True)
        self._media_load_timer.start(500)

    def _attach_video_to_frame(self):
        """将VLC视频输出绑定到video_frame窗口"""
        if sys.platform.startswith('win'):
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform.startswith('darwin'):
            self.media_player.set_nsobject(self.video_frame.winId())

    def showEvent(self, event):
        """当窗口重新显示时，重新绑定VLC视频输出"""
        super().showEvent(event)
        if vlc_available and self._is_media_loaded:
            # 重新绑定视频输出到video_frame
            self._attach_video_to_frame()
            # 刷新当前帧
            if not self._is_playing:
                current_pos = self.media_player.get_time()
                # 播放一帧后暂停以刷新画面
                self.media_player.play()
                QTimer.singleShot(50, lambda: self._refresh_frame_after_show(current_pos))

    def _check_media_loaded(self):
        """Checks if the media has been successfully parsed after a short delay."""
        duration_ms = self.media_player.get_length()
        if duration_ms > 0:
            print(f"[DEBUG VLC] Media loaded successfully. Duration: {duration_ms}ms")
            self._is_media_loaded = True
            self.position_slider.setRange(0, duration_ms)
            self.play_button.setEnabled(True)
            self.position_slider.setEnabled(True)
            # Update play button icon to play state since video is loaded
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.file_label.setText(f"Video: {unquote(os.path.basename(self.media_player.get_media().get_mrl()))}")
            self.change_volume(self.volume_slider.value()) # Set initial volume
        else:
            print("[DEBUG VLC] Failed to get media duration after 500ms.")
            self._on_vlc_error()

    def _refresh_frame_after_show(self, position_ms: int):
        """在showEvent后刷新视频帧"""
        if vlc_available and self._is_media_loaded:
            self.media_player.pause()
            self.media_player.set_time(position_ms)
            self._is_playing = False

    @Slot(int)
    def set_playback_position(self, position_ms: int):
        if self._is_media_loaded:
            # 限制跳转位置在有效范围内
            duration_ms = self.media_player.get_length()
            if duration_ms > 0:
                position_ms = max(0, min(position_ms, duration_ms - 500))
                self.media_player.set_time(position_ms)
                # Reset master clock state on seek
                self.current_time_ms = position_ms
                if self._is_playing:
                    self.playback_start_time = time.perf_counter()
                    self.playback_start_offset_ms = position_ms
                self.last_vlc_time_ms = -1
                self.vlc_read_counter = 0
            # duration_ms <= 0 时不进行跳转，避免崩溃

    def play_clicked(self):
        if not self._is_media_loaded: return
        # When the user clicks play, we do NOT want to auto-pause.
        self._auto_pause_on_play = False
        if not self._is_media_loaded: return

        if self.media_player.is_playing():
            self.master_clock_timer.stop()
            self.media_player.pause()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self._is_playing = False
            self.playback_stopped.emit()  # 发射停止信号
        else:
            # 检查是否在结尾附近，如果是则重新加载视频
            duration_ms = self.media_player.get_length()
            current_time = self.media_player.get_time()
            if duration_ms > 0 and current_time >= duration_ms - 500:
                # 重新加载视频到开头
                if hasattr(self, '_current_video_path') and self._current_video_path:
                    media = self.instance.media_new(self._current_video_path)
                    self.media_player.set_media(media)
                    self._attach_video_to_frame()
            # Initialize master clock
            self.playback_start_time = time.perf_counter()
            self.playback_start_offset_ms = self.current_time_ms
            self.last_vlc_time_ms = -1
            self.vlc_read_counter = 0
            self.master_clock_timer.start()
            self.media_player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self._is_playing = True
            self.playback_started.emit()  # 发射开始信号

    def toggle_playback(self):
        """切换播放/暂停状态（用于外部调用，如空格键）"""
        self.play_clicked()

    def pause(self):
        """暂停播放"""
        if self._is_media_loaded and self.media_player.is_playing():
            self.master_clock_timer.stop()
            self.media_player.pause()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self._is_playing = False
            self.playback_stopped.emit()

    def is_playing(self) -> bool:
        """返回当前是否正在播放"""
        return self._is_playing

    def change_volume(self, volume: int):
        if vlc_available:
            self.media_player.audio_set_volume(volume)

    @Slot()
    def _on_master_tick(self):
        """Master clock tick at 100Hz for smooth playback head updates."""
        if not self._is_playing or not self._is_media_loaded:
            return

        # Use high-precision local clock to calculate elapsed time
        elapsed_sec = time.perf_counter() - self.playback_start_time
        self.current_time_ms = self.playback_start_offset_ms + int(elapsed_sec * 1000)

        # Every 500 ticks (5000ms = 5s), read VLC time for synchronization
        self.vlc_read_counter += 1
        if self.vlc_read_counter >= 500:
            self.vlc_read_counter = 0

            if self.media_player.get_media():
                vlc_time = self.media_player.get_time()
                if vlc_time >= 0:
                    # Only recalibrate if drift exceeds 50ms threshold
                    drift = abs(vlc_time - self.current_time_ms)
                    if drift > 50:
                        self.playback_start_time = time.perf_counter()
                        self.playback_start_offset_ms = vlc_time
                        self.current_time_ms = vlc_time
                        self.last_vlc_time_ms = vlc_time

        # Check if end of media is reached
        duration_ms = self.media_player.get_length()
        if duration_ms > 0 and self.current_time_ms >= duration_ms:
            self.master_clock_timer.stop()
            self._is_playing = False
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.playback_stopped.emit()
            return

        # Update position slider with blocked signals to prevent loops
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(int(self.current_time_ms))
        self.position_slider.blockSignals(False)

        # Emit signal for device output synchronization
        self.position_changed_during_playback.emit(int(self.current_time_ms))



    # --- VLC Event Handlers ---

    @Slot()
    def _on_vlc_media_parsed(self, event):
        """Called when VLC has successfully parsed the media file's metadata."""
        duration_ms = self.media_player.get_length()
        if duration_ms > 0 and not self._is_media_loaded:
            print(f"[DEBUG VLC] Media parsed. Duration: {duration_ms}ms")
            self._is_media_loaded = True
            self.position_slider.setRange(0, duration_ms)
            self.play_button.setEnabled(True)
            self.position_slider.setEnabled(True)
            self.file_label.setText(f"Video: {unquote(os.path.basename(self.media_player.get_media().get_mrl()))}")
            self.change_volume(self.volume_slider.value())

    def _on_vlc_position_changed(self, event):
        # This event gives position as a float 0.0 - 1.0
        # We use the time_changed event instead for more precision
        pass

    def _on_vlc_time_changed(self, event):
        # Master clock timer handles position updates during playback
        # This event is only used for scrubbing feedback
        if self._is_scrubbing:
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(event.u.new_time)
            self.position_slider.blockSignals(False)

    def _on_vlc_end_reached(self, event):
        """播放结束时只暂停，不重新加载"""
        self._is_playing = False
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def _on_vlc_error(self, event=None):
        print("[ERROR VLC] An error was encountered.")
        self.file_label.setText("Error: Could not play media.")
        self.play_button.setEnabled(False)
        self.position_slider.setEnabled(False)
        self._is_media_loaded = False
        if hasattr(self, '_media_load_timer') and self._media_load_timer.isActive():
            self._media_load_timer.stop()

    def _on_vlc_buffering(self, event):
        """Handle buffering event."""
        # Could show buffering indicator if needed
        buffer_percent = event.u.new_cache
        print(f"[DEBUG VLC] Buffering: {buffer_percent}%")

    def _on_vlc_playing(self, event):
        """Handle when playback starts."""
        if self._auto_pause_on_play:
            self.media_player.pause()
            self._auto_pause_on_play = False
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self._is_playing = True

    def _on_vlc_paused(self, event):
        """Handle when playback is paused."""
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._is_playing = False

    # --- Slider Event Handlers ---
    def _slider_pressed(self):
        if not self._is_media_loaded: return
        self._is_scrubbing = True
        # Pause the video but remember if it was playing for later
        if self.media_player.is_playing():
            self._was_playing_before_scrub = True
            self.media_player.pause()
        else:
            self._was_playing_before_scrub = False

    def _slider_scrubbed(self, position: int):
        if not self._is_media_loaded: return
        self.current_time_ms = position
        self.set_playback_position(position)
        self.position_changed_manually.emit(position)

    def _slider_released(self):
        self._is_scrubbing = False
        # Resume playback if it was playing before scrubbing
        if self._was_playing_before_scrub:
            # Reinitialize master clock for resumed playback
            self.playback_start_time = time.perf_counter()
            self.playback_start_offset_ms = self.current_time_ms
            self.last_vlc_time_ms = -1
            self.vlc_read_counter = 0
            self.master_clock_timer.start()
            self.media_player.play()
            self._is_playing = True

    def resizeEvent(self, event):
        """Handle resize events to potentially adjust video display."""
        # The video should automatically scale within the video_frame
        super().resizeEvent(event)
        # If using specific scaling, you might want to adjust video aspect ratio here
        # self.media_player.video_set_scale(0) # 0 means auto-scale

    def get_media_duration(self) -> int:
        """Get the total duration of the loaded media in milliseconds."""
        if self._is_media_loaded:
            return self.media_player.get_length()
        return 0

    def get_current_position(self) -> int:
        """Get the current playback position in milliseconds."""
        if self._is_media_loaded:
            return self.media_player.get_time()
        return 0

    def get_video_dimensions(self) -> tuple:
        """Get the video dimensions (width, height) if available."""
        if self._is_media_loaded:
            try:
                # Get video size using libVLC API
                w, h = self.media_player.video_get_size(0)  # 0 for the first video track
                return w, h
            except:
                # video_get_size might not work for all formats
                return 0, 0
        return 0, 0

    def stop(self):
        """Stop playback and reset player."""
        if vlc_available and self._is_media_loaded:
            self.master_clock_timer.stop()
            self.media_player.stop()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.position_slider.setValue(0)
            # Reset master clock state
            self.current_time_ms = 0
            self.playback_start_time = 0
            self.playback_start_offset_ms = 0
            self.last_vlc_time_ms = -1
            self.vlc_read_counter = 0
            self._is_playing = False

    def set_playback_rate(self, rate: float):
        """Set the playback speed rate (1.0 is normal speed)."""
        if self._is_media_loaded and vlc_available:
            success = self.media_player.set_rate(rate)
            return success
        return False

    def get_playback_rate(self) -> float:
        """Get the current playback speed rate."""
        if self._is_media_loaded and vlc_available:
            return self.media_player.get_rate()
        return 1.0

    def __del__(self):
        """Clean up VLC resources when the widget is destroyed."""
        if vlc_available and hasattr(self, 'media_player'):
            if self.media_player.is_playing():
                self.media_player.stop()
            # Release media and other VLC resources if needed