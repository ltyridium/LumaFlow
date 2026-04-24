import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSlider

from ui.video_player_widget import VideoPlayerWidget


app = QApplication.instance() or QApplication([])


class _TimerStub:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class _MediaPlayerStub:
    def __init__(self, *, length=5000, time_ms=0, playing=False):
        self.length = length
        self.time_ms = time_ms
        self.playing = playing
        self.set_time_calls = []
        self.stop_calls = 0

    def get_length(self):
        return self.length

    def get_time(self):
        return self.time_ms

    def set_time(self, position_ms):
        self.time_ms = position_ms
        self.set_time_calls.append(position_ms)

    def is_playing(self):
        return self.playing

    def pause(self):
        self.playing = False

    def play(self):
        self.playing = True

    def stop(self):
        self.playing = False
        self.time_ms = 0
        self.stop_calls += 1


def build_player(*, length=5000, time_ms=0, playing=False):
    player = VideoPlayerWidget.__new__(VideoPlayerWidget)
    player.time_label = QLabel()
    player.percentage_label = QLabel()
    player.play_button = QPushButton()
    player.volume_slider = QSlider()
    player.style = lambda: QApplication.style()
    player.media_player = _MediaPlayerStub(length=length, time_ms=time_ms, playing=playing)
    player.master_clock_timer = _TimerStub()
    player.position_changed_manually_events = []
    player.position_changed_playback_events = []
    player.playback_stopped_events = []
    player.position_changed_manually = SimpleNamespace(
        emit=lambda value: player.position_changed_manually_events.append(value)
    )
    player.position_changed_during_playback = SimpleNamespace(
        emit=lambda value: player.position_changed_playback_events.append(value)
    )
    player.playback_stopped = SimpleNamespace(
        emit=lambda: player.playback_stopped_events.append(True)
    )
    player._is_media_loaded = True
    player._is_playing = playing
    player._is_fullscreen = False
    player._auto_pause_on_play = False
    player._current_video_path = "demo.mp4"
    player.current_time_ms = time_ms
    player.total_duration_ms = length
    player.playback_start_time = 0.0
    player.playback_start_offset_ms = 0
    player.last_vlc_time_ms = -1
    player.vlc_read_counter = 0
    player.last_reported_vlc_time = -1
    player.smooth_drift = 0.0
    player.last_tick_perf = 1.0
    return player


class VideoPlayerWidgetTests(unittest.TestCase):
    def test_apply_loaded_media_state_updates_time_label_and_percentage(self):
        player = build_player(length=3_723_004, time_ms=0)

        player._apply_loaded_media_state(3_723_004)

        self.assertEqual(3_723_004, player.total_duration_ms)
        self.assertEqual(
            "00:00:00.000 / 01:02:03.004",
            player.time_label.text(),
        )
        self.assertEqual("0.0%", player.percentage_label.text())

    def test_seek_to_time_clamps_and_emits_manual_position_change(self):
        player = build_player(length=5000, time_ms=1000)

        actual_time = player.seek_to_time(4900)

        self.assertEqual(4500, actual_time)
        self.assertEqual([4500], player.media_player.set_time_calls)
        self.assertEqual([4500], player.position_changed_manually_events)
        self.assertEqual("00:00:04.500 / 00:00:05.000", player.time_label.text())
        self.assertEqual("90.0%", player.percentage_label.text())

    def test_master_tick_updates_time_display_percentage_and_playback_signal(self):
        player = build_player(length=5000, time_ms=1000, playing=True)
        player.last_tick_perf = 1.0
        player.media_player.time_ms = 1250

        with patch("ui.video_player_widget.time.perf_counter", return_value=1.01):
            player._on_master_tick()

        self.assertEqual([1012], player.position_changed_playback_events)
        self.assertEqual("00:00:01.012 / 00:00:05.000", player.time_label.text())
        self.assertEqual("20.2%", player.percentage_label.text())

    def test_handle_vlc_paused_syncs_time_label_from_vlc(self):
        player = build_player(length=5000, time_ms=1000, playing=True)
        player.media_player.time_ms = 2345

        player._handle_vlc_paused()

        self.assertEqual(1, player.master_clock_timer.stop_calls)
        self.assertFalse(player._is_playing)
        self.assertEqual(2345, player.current_time_ms)
        self.assertEqual("00:00:02.345 / 00:00:05.000", player.time_label.text())
        self.assertEqual("46.9%", player.percentage_label.text())

    def test_stop_resets_current_position_but_keeps_total_duration_display(self):
        player = build_player(length=5000, time_ms=2345, playing=True)

        player.stop()

        self.assertEqual(1, player.master_clock_timer.stop_calls)
        self.assertEqual(1, player.media_player.stop_calls)
        self.assertFalse(player._is_playing)
        self.assertEqual(0, player.current_time_ms)
        self.assertEqual("00:00:00.000 / 00:00:05.000", player.time_label.text())
        self.assertEqual("0.0%", player.percentage_label.text())


if __name__ == "__main__":
    unittest.main()
