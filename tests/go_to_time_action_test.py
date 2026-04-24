import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from core.i18n import tr
from core.timecode import format_time_ms
from ui.main_window import MainWindow


app = QApplication.instance() or QApplication([])


def make_focus_stub(has_focus: bool):
    return SimpleNamespace(hasFocus=lambda: has_focus)


class GoToTimeActionTests(unittest.TestCase):
    def _build_window(self, *, source_focus=False, edit_focus=False):
        window = MainWindow.__new__(MainWindow)
        window.source_timeline = make_focus_stub(source_focus)
        window.source_audio_track = make_focus_stub(False)
        window.edit_timeline = make_focus_stub(edit_focus)
        window.edit_audio_track = make_focus_stub(False)
        return window

    def test_go_to_time_routes_to_source_preview_when_source_context_is_focused(self):
        window = self._build_window(source_focus=True)
        messages = []
        seek_calls = []
        captured = {}

        window.source_preview_widget = SimpleNamespace(
            get_media_duration=lambda: 5000,
            get_current_position=lambda: 1234,
            seek_to_time=lambda position_ms: seek_calls.append(position_ms) or position_ms,
        )
        window.edit_preview_widget = SimpleNamespace(
            get_media_duration=lambda: 5000,
            get_current_position=lambda: 4321,
            seek_to_time=lambda position_ms: self.fail("Edit preview should not receive the seek"),
        )
        window.set_status_message = messages.append

        def fake_get_text(parent, title, label, text=""):
            captured["text"] = text
            return "00:00:02.345", True

        with patch("ui.main_window.QInputDialog.getText", side_effect=fake_get_text):
            MainWindow.on_go_to_time(window)

        self.assertEqual(format_time_ms(1234), captured["text"])
        self.assertEqual([2345], seek_calls)
        self.assertEqual(
            [tr("status.go_to_time_applied", time=format_time_ms(2345))],
            messages,
        )

    def test_go_to_time_defaults_to_edit_preview_when_no_timeline_has_focus(self):
        window = self._build_window()
        messages = []
        seek_calls = []

        window.source_preview_widget = SimpleNamespace(
            get_media_duration=lambda: 8000,
            get_current_position=lambda: 1111,
            seek_to_time=lambda position_ms: self.fail("Source preview should not receive the default seek"),
        )
        window.edit_preview_widget = SimpleNamespace(
            get_media_duration=lambda: 8000,
            get_current_position=lambda: 2222,
            seek_to_time=lambda position_ms: seek_calls.append(position_ms) or position_ms,
        )
        window.set_status_message = messages.append

        with patch("ui.main_window.QInputDialog.getText", return_value=("3456", True)):
            MainWindow.on_go_to_time(window)

        self.assertEqual([3456], seek_calls)
        self.assertEqual(
            [tr("status.go_to_time_applied", time=format_time_ms(3456))],
            messages,
        )

    def test_go_to_time_requires_loaded_video(self):
        window = self._build_window()
        messages = []
        window.source_preview_widget = SimpleNamespace(get_media_duration=lambda: 0)
        window.edit_preview_widget = SimpleNamespace(get_media_duration=lambda: 0)
        window.set_status_message = messages.append

        with patch("ui.main_window.QInputDialog.getText") as get_text:
            MainWindow.on_go_to_time(window)

        get_text.assert_not_called()
        self.assertEqual([tr("status.go_to_time_requires_video")], messages)

    def test_go_to_time_shows_warning_for_invalid_input(self):
        window = self._build_window(edit_focus=True)
        messages = []

        window.source_preview_widget = SimpleNamespace(get_media_duration=lambda: 0)
        window.edit_preview_widget = SimpleNamespace(
            get_media_duration=lambda: 5000,
            get_current_position=lambda: 2222,
            seek_to_time=lambda position_ms: self.fail("Invalid input should not seek"),
        )
        window.set_status_message = messages.append

        with patch("ui.main_window.QInputDialog.getText", return_value=("oops", True)):
            with patch("ui.main_window.QMessageBox.warning") as warning:
                MainWindow.on_go_to_time(window)

        warning.assert_called_once_with(
            window,
            tr("dialog.go_to_time.invalid_title"),
            tr("dialog.go_to_time.invalid_message"),
        )
        self.assertEqual([], messages)


if __name__ == "__main__":
    unittest.main()
