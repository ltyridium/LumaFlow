import unittest
from types import SimpleNamespace

import pandas as pd

from ui.timeline_widget import IDXIndicatorsItem, TimelineWidget


class _TimerStub:
    def __init__(self, active=False):
        self.active = active
        self.stop_calls = 0
        self.start_calls = []

    def isActive(self):
        return self.active

    def stop(self):
        self.active = False
        self.stop_calls += 1

    def start(self, interval_ms):
        self.active = True
        self.start_calls.append(interval_ms)


class _UpdateStub:
    def __init__(self):
        self.update_calls = 0

    def update(self):
        self.update_calls += 1


class _PlaybackHeadStub(_UpdateStub):
    def __init__(self):
        super().__init__()
        self._value = 0.0
        self.set_value_calls = []

    def setValue(self, value):
        self._value = value
        self.set_value_calls.append(value)

    def value(self):
        return self._value


class _IDXBoundsStub:
    def __init__(self):
        self.timeline_bounds_calls = []

    def setTimelineBounds(self, start_ms, end_ms):
        self.timeline_bounds_calls.append((start_ms, end_ms))


class TimelineViewportRefreshTests(unittest.TestCase):
    def test_idx_indicator_bounds_cover_long_timeline(self):
        item = IDXIndicatorsItem()
        long_timeline_end_ms = 10_740_000.0

        item.setTimelineBounds(0.0, long_timeline_end_ms)

        self.assertGreater(item.boundingRect().right(), long_timeline_end_ms)

    def test_sync_idx_indicator_bounds_uses_timeline_limit(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        widget.idx_indicators_item = _IDXBoundsStub()
        widget._get_timeline_limit_ms = lambda: 10_740_000.0

        TimelineWidget._sync_idx_indicator_bounds(widget)

        self.assertEqual([(0.0, 10_740_000.0)], widget.idx_indicators_item.timeline_bounds_calls)

    def test_sync_idx_indicator_bounds_resets_without_limit(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        widget.idx_indicators_item = _IDXBoundsStub()
        widget._get_timeline_limit_ms = lambda: None

        TimelineWidget._sync_idx_indicator_bounds(widget)

        self.assertEqual([(None, None)], widget.idx_indicators_item.timeline_bounds_calls)

    def _build_widget_for_viewport_change(self, *, has_data=True):
        widget = TimelineWidget.__new__(TimelineWidget)
        widget.current_data = pd.DataFrame({"frame_time_ms": [0.0]}) if has_data else pd.DataFrame()
        widget.viewport_change_timer = _TimerStub()
        widget.scatter_item = _UpdateStub()
        widget.idx_indicators_item = _UpdateStub()
        widget.playback_head = _UpdateStub()
        widget.viewport_item = _UpdateStub()
        widget.viewport = lambda: widget.viewport_item
        widget.update_zoom_label = lambda: setattr(widget, "zoom_updated", True)
        widget._update_marker_text_visibility = lambda: setattr(widget, "markers_updated", True)
        return widget

    def test_viewport_change_starts_deferred_render_timer(self):
        widget = self._build_widget_for_viewport_change(has_data=True)

        TimelineWidget.on_viewport_changed(widget, object())

        self.assertTrue(widget.zoom_updated)
        self.assertTrue(widget.markers_updated)
        self.assertEqual(0, widget.viewport_change_timer.stop_calls)
        self.assertEqual([10], widget.viewport_change_timer.start_calls)
        self.assertEqual(1, widget.scatter_item.update_calls)
        self.assertEqual(1, widget.idx_indicators_item.update_calls)
        self.assertEqual(1, widget.playback_head.update_calls)
        self.assertEqual(1, widget.viewport_item.update_calls)

    def test_viewport_change_keeps_active_render_timer_alive(self):
        widget = self._build_widget_for_viewport_change(has_data=True)
        widget.viewport_change_timer = _TimerStub(active=True)

        TimelineWidget.on_viewport_changed(widget)

        self.assertEqual(0, widget.viewport_change_timer.stop_calls)
        self.assertEqual([], widget.viewport_change_timer.start_calls)

    def test_viewport_change_does_not_schedule_render_for_empty_data(self):
        widget = self._build_widget_for_viewport_change(has_data=False)

        TimelineWidget.on_viewport_changed(widget)

        self.assertEqual(0, widget.viewport_change_timer.stop_calls)
        self.assertEqual([], widget.viewport_change_timer.start_calls)

    def test_viewport_timer_creates_render_request(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        calls = []
        widget._schedule_render = lambda reason: calls.append(reason)

        TimelineWidget._schedule_viewport_render_from_timer(widget)

        self.assertEqual(["viewport_changed"], calls)

    def test_set_view_range_clamped_triggers_viewport_refresh(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        set_range_calls = []
        refresh_calls = []
        widget.clamp_view_range = lambda start, end: (10.0, 110.0)
        widget.plot_item = SimpleNamespace(
            setXRange=lambda start, end, padding=0: set_range_calls.append((start, end, padding))
        )
        widget.on_viewport_changed = lambda: refresh_calls.append(True)

        result = TimelineWidget.set_view_range_clamped(widget, 0.0, 200.0)

        self.assertEqual((10.0, 110.0), result)
        self.assertEqual([(10.0, 110.0, 0)], set_range_calls)
        self.assertEqual([True], refresh_calls)

    def test_set_view_range_clamped_does_not_duplicate_signal_refresh(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        refresh_calls = []
        widget.clamp_view_range = lambda start, end: (10.0, 110.0)

        def set_x_range(_start, _end, padding=0):
            widget._range_change_signal_received = True

        widget.plot_item = SimpleNamespace(setXRange=set_x_range)
        widget.on_viewport_changed = lambda: refresh_calls.append(True)

        result = TimelineWidget.set_view_range_clamped(widget, 0.0, 200.0)

        self.assertEqual((10.0, 110.0), result)
        self.assertEqual([], refresh_calls)

    def test_set_playback_head_time_refreshes_indicators_when_signals_are_blocked(self):
        widget = TimelineWidget.__new__(TimelineWidget)
        widget.playback_head = _PlaybackHeadStub()
        widget.idx_indicators_item = _UpdateStub()
        indicator_calls = []
        widget._update_idx_indicators = lambda: indicator_calls.append(widget.playback_head.value())

        TimelineWidget.set_playback_head_time(widget, 250.0)

        self.assertEqual([250.0], widget.playback_head.set_value_calls)
        self.assertEqual([250.0], indicator_calls)
        self.assertEqual(1, widget.playback_head.update_calls)
        self.assertEqual(1, widget.idx_indicators_item.update_calls)


if __name__ == "__main__":
    unittest.main()
