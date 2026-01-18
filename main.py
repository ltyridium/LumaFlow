import sys
import shutil
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSettings
from ui.main_window import MainWindow
from app_logic import AppLogic
from PySide6.QtGui import QIcon

def check_dependencies():
    """Check if required external dependencies (VLC, FFmpeg) are available."""
    missing = []

    # Check for VLC
    try:
        import vlc
        # Try to instantiate vlc to see if the DLLs are actually found
        try:
            instance = vlc.Instance()
            instance.release()
        except Exception:
             missing.append("VLC Media Player (libvlc)")
    except ImportError:
        missing.append("python-vlc module")

    # Check for FFmpeg
    if shutil.which('ffmpeg') is None:
        missing.append("FFmpeg")

    if missing:
        app = QApplication.instance() or QApplication(sys.argv)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Missing Dependencies")
        msg.setText("The following required dependencies are missing or not found in PATH:")
        msg.setInformativeText("\n".join(f"- {item}" for item in missing) +
                             "\n\nPlease install them and try again.\n" +
                             "For VLC: Install VLC Media Player (ensure bitness matches Python)\n" +
                             "For FFmpeg: Download and add to system PATH")
        msg.exec()
        return False

    return True

if __name__ == "__main__":
    app = QApplication(sys.argv)

    if not check_dependencies():
        sys.exit(1)

    logic = AppLogic()
    window = MainWindow(logic)
    app.setWindowIcon(QIcon('resources/icons/icon.png'))
    # Connect signals from window to logic
    window.new_edit_requested.connect(logic.new_edit)
    window.open_requested.connect(logic.open_file)
    window.open_source_requested.connect(logic.open_source_file)
    window.save_requested.connect(logic.save_file)
    window.cut_requested.connect(logic.cut_selection)
    window.copy_requested.connect(logic.copy_selection)
    window.paste_requested.connect(logic.paste_selection)
    window.delete_requested.connect(logic.delete_selection)
    window.undo_requested.connect(logic.undo)
    window.redo_requested.connect(logic.redo)
    
    # Connect offset signal
    window.edit_timeline.offset_requested.connect(logic.offset_selection)
    window.source_timeline.offset_requested.connect(logic.offset_selection)

    # Connect video playback position to device output
    window.edit_preview_widget.position_changed_during_playback.connect(
        lambda pos: logic.on_playback_position_changed(pos, 'edit')
    )
    window.edit_preview_widget.playback_started.connect(
        logic.reset_device_tracking
    )
    window.source_preview_widget.position_changed_during_playback.connect(
        lambda pos: logic.on_playback_position_changed(pos, 'source')
    )
    window.source_preview_widget.playback_started.connect(
        logic.reset_device_tracking
    )

    # Connect timeline-specific copy signals (these are already connected in MainWindow, but we'll add direct connections too)
    # Actually, let's rely on the MainWindow connections to handle the source timeline copy differently
    
    # Restore window geometry and state
    settings = QSettings("LumaFlow", "LumaFlow")
    if settings.value("geometry"):
        window.restoreGeometry(settings.value("geometry"))
    if settings.value("windowState"):
        window.restoreState(settings.value("windowState"))
    
    window.show()
    
    sys.exit(app.exec())
