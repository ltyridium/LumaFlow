"""
TimelineGroupWidget - Atomic container for Timeline + AudioTrack
Per PRD 2.1: This container ensures visual alignment between lighting data and audio waveforms.
"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter

from .timeline_widget import TimelineWidget
from .audio_track_widget import AudioTrackWidget


class TimelineGroupWidget(QWidget):
    """
    Atomic container combining TimelineWidget and AudioTrackWidget.
    These two components must never be separated to ensure visual alignment.
    """
    # Forward signals from timeline
    region_selected = Signal(float, float)
    playback_head_changed = Signal(float)
    add_marker_requested = Signal(float, str)
    update_marker_requested = Signal(float, str)  # Matches TimelineWidget signature
    copy_requested = Signal(float, float, str)
    cut_requested = Signal(float, float)
    paste_requested = Signal(float)
    delete_requested = Signal(float, float)
    insert_blackout_requested = Signal(float)
    insert_color_dialog_requested = Signal(float)

    # Audio track signals
    x_range_changed = Signal(float, float)

    def __init__(self, timeline_type: str = 'edit', audio_manager=None, parent=None):
        super().__init__(parent)
        self.timeline_type = timeline_type
        self._syncing_audio = False

        self._init_ui(audio_manager)
        self._connect_signals()

    def _init_ui(self, audio_manager):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Vertical splitter: Timeline (top) + AudioTrack (bottom)
        self.splitter = QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter)

        # Timeline widget
        self.timeline = TimelineWidget(timeline_type=self.timeline_type)
        self.splitter.addWidget(self.timeline)

        # Audio track widget
        self.audio_track = AudioTrackWidget(audio_manager=audio_manager)
        # 默认显示音频轨道
        self.splitter.addWidget(self.audio_track)

        # Default sizes
        self.splitter.setSizes([400, 80])

    def _connect_signals(self):
        # Forward timeline signals
        self.timeline.region_selected.connect(self.region_selected)
        self.timeline.playback_head_changed.connect(self.playback_head_changed)
        self.timeline.add_marker_requested.connect(self.add_marker_requested)
        self.timeline.update_marker_requested.connect(self.update_marker_requested)
        self.timeline.copy_requested.connect(self.copy_requested)

        if self.timeline_type == 'edit':
            self.timeline.cut_requested.connect(self.cut_requested)
            self.timeline.paste_requested.connect(self.paste_requested)
            self.timeline.delete_requested.connect(self.delete_requested)
            self.timeline.insert_blackout_requested.connect(self.insert_blackout_requested)
            self.timeline.insert_color_dialog_requested.connect(self.insert_color_dialog_requested)

        # Sync timeline <-> audio track X range
        self.timeline.plot_item.vb.sigRangeChanged.connect(self._sync_audio_to_timeline)
        self.audio_track.x_range_changed.connect(self._sync_timeline_to_audio)

        # Sync playback head
        self.timeline.playback_head.sigPositionChanged.connect(
            lambda: self.audio_track.set_playback_head_time(self.timeline.get_playback_head_time())
        )

        # Audio vertical zoom
        self.timeline.audio_vertical_zoom_requested.connect(self._on_audio_vertical_zoom)

    def _on_audio_vertical_zoom(self, delta: float):
        """Handle audio vertical zoom request from timeline"""
        if self.audio_track.isVisible():
            self.audio_track.zoom_vertical(delta)

    def _sync_audio_to_timeline(self):
        """Sync audio track X range to timeline"""
        if self._syncing_audio or not self.audio_track.isVisible():
            return
        self._syncing_audio = True
        x_range = self.timeline.plot_item.viewRange()[0]
        self.audio_track.set_x_range(x_range[0], x_range[1])
        self._syncing_audio = False

    def _sync_timeline_to_audio(self, x_min: float, x_max: float):
        """Sync timeline X range to audio track with zoom clamping"""
        if self._syncing_audio:
            return
        self._syncing_audio = True

        light_range = self.timeline.plot_item.viewRange()[0]
        light_width = light_range[1] - light_range[0]
        audio_width = x_max - x_min

        # Clamp zoom: use the larger range
        if audio_width > light_width:
            center = (x_min + x_max) / 2
            x_min = center - light_width / 2
            x_max = center + light_width / 2

        self.timeline.plot_item.setXRange(x_min, x_max, padding=0)
        self._syncing_audio = False

    # --- Public API ---

    def set_data(self, df, auto_zoom=False):
        """Set timeline data"""
        self.timeline.set_data(df, auto_zoom=auto_zoom)

    def set_audio_data(self, audio_data):
        """Set audio visualization data"""
        self.audio_track.set_audio_data(audio_data)

    def show_audio_track(self, show: bool = True):
        """Show or hide the audio track"""
        if show:
            x_range = self.timeline.plot_item.viewRange()[0]
            self.audio_track.set_x_range(x_range[0], x_range[1])
            self.audio_track.set_playback_head_time(self.timeline.get_playback_head_time())
            self.audio_track.show()
        else:
            self.audio_track.hide()

    def set_audio_height(self, height: float):
        """Adjust audio track height ratio (0.5-5.0)"""
        sizes = self.splitter.sizes()
        total = sum(sizes)
        audio_h = int(total * height / 5)
        self.splitter.setSizes([total - audio_h, audio_h])

    def set_colormap(self, colormap: str):
        """Set audio track colormap"""
        self.audio_track.set_colormap(colormap)

    def get_playback_head_time(self) -> float:
        return self.timeline.get_playback_head_time()

    def set_playback_head_time(self, time_ms: float):
        self.timeline.set_playback_head_time(time_ms)
        self.audio_track.set_playback_head_time(time_ms)

    def get_selected_region(self):
        return self.timeline.get_selected_region()

    def set_selected_region(self, start_ms: float, end_ms: float):
        self.timeline.set_selected_region(start_ms, end_ms)

    def shutdown(self):
        """Clean shutdown"""
        self.timeline.shutdown()
