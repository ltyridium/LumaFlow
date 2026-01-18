import sys
import os
import pandas as pd
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QMessageBox, QInputDialog, QSplitter,
    QStyle, QToolBar, QDockWidget
)

# Assuming these are in the correct project structure
from .timeline_group_widget import TimelineGroupWidget
from .widgets import DataTableWidget
from .dialogs import EffectDialog, ColorPickerDialog
from .audio_controls_widget import AudioControlsWidget
from .audio_settings_dialog import AudioSettingsDialog
from .video_player_widget import VideoPlayerWidget
from .device_output_dock import DeviceOutputWidget

class MainWindow(QMainWindow):
    # Signals to be connected to the AppLogic controller
    open_requested = Signal(str)
    open_source_requested = Signal(str)
    save_requested = Signal(str)
    new_edit_requested = Signal(float)
    cut_requested = Signal(float, float, str)
    copy_requested = Signal(float, float, str)
    paste_requested = Signal(float, str)
    delete_requested = Signal(float, float, str)
    undo_requested = Signal()
    redo_requested = Signal()
    add_marker_requested = Signal(float, str)
    insert_blackout_requested = Signal(float)
    insert_color_frame_requested = Signal(float, dict, int, str) # at_ms, color, function, marker
    generate_breathing_effect_requested = Signal(dict)
    generate_rainbow_effect_requested = Signal(dict)

    def __init__(self, app_logic, parent=None):
        super().__init__(parent)
        self.logic = app_logic
        self.setWindowTitle("LumaFlow")
        self.setGeometry(100, 100, 1600, 900) # [FIXED] Corrected window height

        self.should_auto_zoom = True
        self.is_initial_load = True

        # Flags to prevent feedback loops during video synchronization
        self.syncing_source_video_to_timeline = False
        self.syncing_edit_video_to_timeline = False
        self.syncing_timeline_to_source_video = False
        self.syncing_timeline_to_edit_video = False

        self.create_actions()
        self.init_ui() # init_ui now depends on actions for context menus
        self.addToolBar(Qt.TopToolBarArea, self.create_tool_bar())
        self.create_menus()
        self.connect_signals()
        self.connect_logic_signals()

    def init_ui(self):
        """
        Initialize UI with QDockWidget system per PRD 2.2.
        Layout:
        - Central Widget: Master Sequence (Edit TimelineGroup) - cannot be closed
        - Top Dock: Source Monitor (Source TimelineGroup)
        - Bottom Dock: Data Table
        - Left Top Dock: Source Preview (Video)
        - Left Bottom Dock: Program Preview (Video)
        """
        # --- Central Widget: Master Sequence (Edit Timeline) ---
        # Per PRD 2.2: Cannot be closed, only hidden by other docks
        self.edit_timeline_group = TimelineGroupWidget(
            timeline_type='edit',
            audio_manager=self.logic.audio_manager
        )
        self.setCentralWidget(self.edit_timeline_group)

        # Convenience aliases for backward compatibility
        self.edit_timeline = self.edit_timeline_group.timeline
        self.edit_audio_track = self.edit_timeline_group.audio_track

        # --- Top Dock: Source Monitor ---
        self.source_dock = QDockWidget("Source Monitor", self)
        self.source_dock.setObjectName("SourceMonitorDock")
        self.source_timeline_group = TimelineGroupWidget(
            timeline_type='source',
            audio_manager=self.logic.audio_manager
        )
        self.source_dock.setWidget(self.source_timeline_group)
        self.addDockWidget(Qt.TopDockWidgetArea, self.source_dock)
        self.source_dock.hide()  # 默认隐藏 source 区

        # Convenience aliases
        self.source_timeline = self.source_timeline_group.timeline
        self.source_audio_track = self.source_timeline_group.audio_track

        # --- Bottom Dock: Data Table ---
        self.data_table_dock = QDockWidget("Data Table", self)
        self.data_table_dock.setObjectName("DataTableDock")
        self.data_table = DataTableWidget()
        self.data_table_dock.setWidget(self.data_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.data_table_dock)

        # --- Left Top Dock: Source Preview (Video) ---
        self.source_preview_dock = QDockWidget("Source Preview", self)
        self.source_preview_dock.setObjectName("SourcePreviewDock")
        self.source_preview_widget = VideoPlayerWidget()
        self.source_preview_dock.setWidget(self.source_preview_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.source_preview_dock)
        self.source_preview_dock.hide()  # 默认隐藏 source 预览

        # --- Left Bottom Dock: Program Preview (Video) ---
        self.edit_preview_dock = QDockWidget("Program Preview", self)
        self.edit_preview_dock.setObjectName("ProgramPreviewDock")
        self.edit_preview_widget = VideoPlayerWidget()
        self.edit_preview_dock.setWidget(self.edit_preview_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.edit_preview_dock)

        # Stack video docks vertically
        self.splitDockWidget(self.source_preview_dock, self.edit_preview_dock, Qt.Vertical)

        # --- Audio Controls (in dialog) ---
        self.source_audio_controls = AudioControlsWidget('source')
        self.edit_audio_controls = AudioControlsWidget('edit')
        self.audio_settings_dialog = None

        # --- Right Dock: Device Output ---
        self.device_output_dock = QDockWidget("Device Output", self)
        self.device_output_dock.setObjectName("DeviceOutputDock")
        self.device_output_widget = DeviceOutputWidget()
        self.device_output_dock.setWidget(self.device_output_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.device_output_dock)
        self.device_output_dock.hide()  # Hidden by default

        # Connect video player signals
        self.source_preview_widget.position_changed_manually.connect(self.sync_timeline_to_source_video)
        self.edit_preview_widget.position_changed_manually.connect(self.sync_timeline_to_edit_video)
        self.source_preview_widget.position_changed_during_playback.connect(self.sync_timeline_to_source_video)
        self.edit_preview_widget.position_changed_during_playback.connect(self.sync_timeline_to_edit_video)

        # Playback mutual exclusion
        self.source_preview_widget.playback_started.connect(self._on_source_playback_started)
        self.edit_preview_widget.playback_started.connect(self._on_edit_playback_started)

        # --- Status Bar ---
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

        # Apply dark theme by default on startup
        QTimer.singleShot(0, lambda: self.set_theme("dark_theme"))

        # Restore window state if available
        self._restore_window_state()

    # [MODIFIED] The toolbar is now the primary hub for common actions.
    def create_tool_bar(self):
        """Creates and configures the main application toolbar with logical groupings."""
        tool_bar = QToolBar("Main ToolBar")
        tool_bar.setObjectName("MainToolBar")  # Needed for saveState/restoreState
        tool_bar.setMovable(False)

        # --- Group 1: File Operations ---
        tool_bar.addAction(self.new_edit_action)
        tool_bar.addAction(self.open_source_action)
        tool_bar.addAction(self.open_action)
        tool_bar.addAction(self.save_action)
        tool_bar.addSeparator()

        # --- Group 2: History ---
        tool_bar.addAction(self.undo_action)
        tool_bar.addAction(self.redo_action)
        tool_bar.addSeparator()

        # --- Group 3: Editing ---
        tool_bar.addAction(self.cut_action)
        tool_bar.addAction(self.copy_action)
        tool_bar.addAction(self.paste_action)
        tool_bar.addAction(self.delete_action)
        tool_bar.addSeparator()

        # --- Group 4: Timeline Tools ---
        tool_bar.addAction(self.add_marker_action)
        tool_bar.addAction(self.insert_blackout_action)
        tool_bar.addAction(self.insert_color_action)
        tool_bar.addSeparator()

        # --- Group 5: View Control ---
        tool_bar.addAction(self.fit_view_action)

        # --- Group 6: Video Controls ---
        tool_bar.addSeparator()
        tool_bar.addAction(self.import_source_video_action)
        tool_bar.addAction(self.import_edit_video_action)
        tool_bar.addAction(self.sync_playback_action)

        return tool_bar

    # [MODIFIED] Added more standard icons to actions for a richer toolbar experience.
    def create_actions(self):
        # File actions
        self.new_edit_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "&New Edit...", self)
        self.new_edit_action.setShortcut(QKeySequence.New)
        self.open_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), "&Open Edit...", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_source_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), "Open &Source...", self)
        self.save_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "&Save", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action = QAction("Save &As...", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.exit_action = QAction("E&xit", self)
        self.exit_action.setShortcut(QKeySequence.Quit)

        # Edit actions
        self.undo_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft), "&Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight), "&Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.cut_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton), "Cu&t", self)
        self.cut_action.setShortcut(QKeySequence.Cut)
        self.copy_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon), "&Copy", self)
        self.copy_action.setShortcut(QKeySequence.Copy)
        self.paste_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "&Paste", self)
        self.paste_action.setShortcut(QKeySequence.Paste)
        self.delete_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "&Delete", self)
        self.delete_action.setShortcut(QKeySequence.Delete)

        # View actions
        self.dark_theme_action = QAction("Dark Theme", self)
        self.light_theme_action = QAction("Light Theme", self)
        self.calibration_action = QAction("RGB Calibration...", self)
        self.fit_view_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), "Fit to View", self)
        self.fit_view_action.setShortcut("F")

        # Timeline actions
        self.add_marker_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Add Marker", self)
        self.add_marker_action.setShortcut("M")
        self.insert_blackout_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), "Insert Blackout Frame", self)
        self.insert_blackout_action.setShortcut("B")
        self.insert_color_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton), "Insert Color Frame", self)
        self.insert_color_action.setShortcut("I")

        # Per PRD 5.1: Edit Frame action
        self.edit_frame_action = QAction("Edit Frame", self)
        self.edit_frame_action.setShortcut("E")

        # Generate actions (remain in menu as they are less frequent)
        self.generate_breathing_action = QAction("Generate Breathing Effect", self)
        self.generate_rainbow_action = QAction("Generate Rainbow Effect", self)

        # Offset actions (remain in menu)
        self.offset_dialog_action = QAction("Specify Offset...", self)
        self.offset_dialog_action.setShortcut("Shift+M")
        self.offset_left_action = QAction("Offset Left 100ms", self)
        self.offset_left_action.setShortcut("Ctrl+[")
        self.offset_right_action = QAction("Offset Right 100ms", self)
        self.offset_right_action.setShortcut("Ctrl+]")

        # Video actions
        self.import_source_video_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Import Source Video...", self)
        self.import_edit_video_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Import Edit Video...", self)
        self.sync_playback_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Sync Playback", self)
        self.sync_playback_action.setCheckable(True)
        self.sync_playback_action.setChecked(True)

        # Help actions
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.on_about)

    def create_menus(self):
        # File menu
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_edit_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_source_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_source_video_action)
        file_menu.addAction(self.import_edit_video_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # Edit menu
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)

        # View menu - Per PRD 2.3: Toggle actions for all Docks
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.dark_theme_action)
        view_menu.addAction(self.light_theme_action)
        view_menu.addSeparator()
        view_menu.addAction(self.calibration_action)
        view_menu.addAction(self.fit_view_action)
        view_menu.addSeparator()

        # Dock toggle actions
        view_menu.addAction(self.source_dock.toggleViewAction())
        view_menu.addAction(self.data_table_dock.toggleViewAction())
        view_menu.addAction(self.source_preview_dock.toggleViewAction())
        view_menu.addAction(self.edit_preview_dock.toggleViewAction())
        view_menu.addAction(self.device_output_dock.toggleViewAction())

        # Timeline menu
        timeline_menu = self.menuBar().addMenu("&Timeline")
        timeline_menu.addAction(self.add_marker_action)
        timeline_menu.addAction(self.edit_frame_action)  # Per PRD 5.1
        insert_menu = timeline_menu.addMenu("Insert")
        insert_menu.addAction(self.insert_blackout_action)
        insert_menu.addAction(self.insert_color_action)
        generate_menu = timeline_menu.addMenu("Generate")
        generate_menu.addAction(self.generate_breathing_action)
        generate_menu.addAction(self.generate_rainbow_action)
        timeline_menu.addSeparator()
        offset_menu = timeline_menu.addMenu("Offset")
        offset_menu.addAction(self.offset_dialog_action)
        offset_menu.addAction(self.offset_left_action)
        offset_menu.addAction(self.offset_right_action)

        # Audio menu
        audio_menu = self.menuBar().addMenu("Audio")
        self.audio_settings_action = QAction("Audio Visualization Settings...", self)
        audio_menu.addAction(self.audio_settings_action)

        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

    def connect_signals(self):
        # Connect actions to their handlers
        self.new_edit_action.triggered.connect(self.on_new_edit)
        self.open_action.triggered.connect(self.on_open_clicked)
        self.open_source_action.triggered.connect(self.on_open_source_clicked)
        self.save_action.triggered.connect(lambda: self.save_requested.emit(None))
        self.save_as_action.triggered.connect(self.on_save_as_clicked)
        self.exit_action.triggered.connect(self.close)

        self.cut_action.triggered.connect(self.on_cut)
        self.copy_action.triggered.connect(self.on_copy)
        self.paste_action.triggered.connect(self.on_paste)
        self.delete_action.triggered.connect(self.on_delete)

        self.undo_action.triggered.connect(self.undo_requested.emit)
        self.redo_action.triggered.connect(self.redo_requested.emit)

        self.dark_theme_action.triggered.connect(lambda: self.set_theme("dark_theme"))
        self.light_theme_action.triggered.connect(lambda: self.set_theme("light_theme"))
        self.calibration_action.triggered.connect(self.on_open_calibration)
        self.fit_view_action.triggered.connect(self.on_fit_to_view)

        self.add_marker_action.triggered.connect(self.on_add_marker)
        self.insert_blackout_action.triggered.connect(lambda: self.insert_blackout_requested.emit(self.edit_timeline.get_playback_head_time()))
        self.insert_color_action.triggered.connect(self.on_insert_color_frame)
        self.edit_frame_action.triggered.connect(self.on_edit_frame)  # Per PRD 5.1
        self.generate_breathing_action.triggered.connect(self.on_generate_breathing)
        self.generate_rainbow_action.triggered.connect(self.on_generate_rainbow)

        self.offset_dialog_action.triggered.connect(self.on_show_offset_dialog)
        self.offset_left_action.triggered.connect(lambda: self.on_apply_offset(-100))
        self.offset_right_action.triggered.connect(lambda: self.on_apply_offset(100))

        # Video import and sync actions
        self.import_source_video_action.triggered.connect(self.on_import_source_video)
        self.import_edit_video_action.triggered.connect(self.on_import_edit_video)
        self.sync_playback_action.triggered.connect(self.on_toggle_sync_playback)

        # Audio settings action
        self.audio_settings_action.triggered.connect(self.on_open_audio_settings)

        # Timeline group signals
        self.edit_timeline_group.region_selected.connect(self.on_edit_region_selected)
        self.source_timeline_group.region_selected.connect(self.on_source_region_selected)

        # Audio control connections
        self.source_audio_controls.visibility_changed.connect(self._on_source_audio_visibility_changed)
        self.edit_audio_controls.visibility_changed.connect(self._on_edit_audio_visibility_changed)
        self.source_audio_controls.height_changed.connect(self._on_source_audio_height_changed)
        self.edit_audio_controls.height_changed.connect(self._on_edit_audio_height_changed)
        self.source_audio_controls.channel_mode_changed.connect(self._on_source_audio_channel_changed)
        self.edit_audio_controls.channel_mode_changed.connect(self._on_edit_audio_channel_changed)
        self.source_audio_controls.colormap_changed.connect(self._on_source_audio_colormap_changed)
        self.edit_audio_controls.colormap_changed.connect(self._on_edit_audio_colormap_changed)
        self.source_audio_controls.processing_params_changed.connect(self._on_source_audio_params_changed)
        self.edit_audio_controls.processing_params_changed.connect(self._on_edit_audio_params_changed)

        # Device output connections
        self._connect_device_output_signals()

    def connect_logic_signals(self):
        # Connect signals from the logic controller to UI update slots
        self.logic.timeline_data_changed.connect(self.on_timeline_data_changed)
        self.logic.source_data_changed.connect(self.on_source_data_changed)
        self.logic.status_message_changed.connect(self.set_status_message)
        self.logic.undo_stack_changed.connect(self.set_undo_enabled)
        self.logic.redo_stack_changed.connect(self.set_redo_enabled)
        self.logic.offset_applied.connect(self.on_offset_applied)

        # Audio processing signals
        self.logic.source_audio_processed.connect(self._on_source_audio_data_ready)
        self.logic.edit_audio_processed.connect(self._on_edit_audio_data_ready)
        self.logic.audio_processing_failed.connect(self._on_audio_processing_failed)
        self.logic.audio_progress.connect(self._on_audio_progress)

        # Device output signals
        self.logic.serial_connection_changed.connect(
            lambda connected, msg: self.device_output_widget.serial_panel.set_connected(connected)
        )
        self.logic.keyboard_connection_changed.connect(
            lambda connected, msg: self.device_output_widget.keyboard_panel.set_connected(connected)
        )
        self.logic.serial_frame_sent.connect(
            self.device_output_widget.serial_panel.update_frames_sent
        )
        self.logic.keyboard_frame_sent.connect(
            self.device_output_widget.keyboard_panel.update_frames_sent
        )

        # Connect UI requests to the logic controller
        self.add_marker_requested.connect(self.logic.add_marker)
        self.insert_blackout_requested.connect(self.logic.insert_blackout_frame)
        self.insert_color_frame_requested.connect(self.logic.insert_color_frame)
        self.generate_breathing_effect_requested.connect(self.logic.generate_breathing_effect)
        self.generate_rainbow_effect_requested.connect(self.logic.generate_rainbow_effect)

        # Connect signals from timeline widgets directly to the logic controller
        self.source_timeline.add_marker_requested.connect(self.logic.add_marker)
        self.source_timeline.update_marker_requested.connect(self.logic.update_marker)
        self.source_timeline.copy_requested.connect(self.logic.copy_selection)

        self.edit_timeline.add_marker_requested.connect(self.logic.add_marker)
        self.edit_timeline.update_marker_requested.connect(self.logic.update_marker)
        self.edit_timeline.insert_blackout_requested.connect(self.logic.insert_blackout_frame)
        self.edit_timeline.insert_color_dialog_requested.connect(self.on_insert_color_frame_at_position)
        self.edit_timeline.copy_requested.connect(self.logic.copy_selection)
        self.edit_timeline.cut_requested.connect(self.logic.cut_selection)
        self.edit_timeline.paste_requested.connect(self.logic.paste_selection)
        self.edit_timeline.delete_requested.connect(self.logic.delete_selection)
        
        # Connect timeline playback head changes to video player synchronization
        self.source_timeline_group.playback_head_changed.connect(self.sync_source_video_to_timeline)
        self.edit_timeline_group.playback_head_changed.connect(self.sync_edit_video_to_timeline)

        # Also connect the direct position change signals from the playback head
        # This ensures manual dragging of the playback head updates the video
        self.source_timeline.playback_head.sigPositionChanged.connect(self.on_source_timeline_playback_head_changed)
        self.edit_timeline.playback_head.sigPositionChanged.connect(self.on_edit_timeline_playback_head_changed)

    # --- Action Handlers ---

    def on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Edit CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self.open_requested.emit(file_path)

    def on_open_source_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Source CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self.open_source_requested.emit(file_path)

    def on_save_as_clicked(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV File", "", "CSV Files (*.csv)")
        if file_path:
            self.save_requested.emit(file_path)

    def on_new_edit(self):
        duration_sec, ok = QInputDialog.getDouble(self, "New Edit", "Enter total duration (seconds):", 9600, 1.0, 10000.0, 2)
        if ok and duration_sec > 0:
            self.new_edit_requested.emit(duration_sec)

    def on_add_marker(self):
        active_timeline = self.get_active_timeline()
        if not active_timeline: return
        name, ok = QInputDialog.getText(self, "Add Marker", "Marker Name:")
        if ok and name:
            self.add_marker_requested.emit(active_timeline.get_playback_head_time(), name)

    def on_insert_color_frame(self):
        dialog = ColorPickerDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            self.insert_color_frame_requested.emit(
                self.edit_timeline.get_playback_head_time(),
                values['color'],
                values['function'],
                values['marker']
            )

    def on_insert_color_frame_at_position(self, at_ms):
        dialog = ColorPickerDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            self.insert_color_frame_requested.emit(at_ms, values['color'], values['function'], values['marker'])

    def on_edit_frame(self):
        """
        Per PRD 5.1: Edit Frame (E shortcut).
        1. Find the keyframe closest to playhead (±50ms tolerance)
        2. Open ColorPickerDialog pre-filled with frame's RGB and Function
        3. On Save: Execute UpdateFrameCommand
        """
        if self.edit_timeline.timeline_type != 'edit':
            self.set_status_message("Edit Frame is only available on the edit timeline.")
            return

        playhead_time = self.edit_timeline.get_playback_head_time()
        frame_row, frame_time = self.edit_timeline.get_frame_at_time(playhead_time, tolerance_ms=50.0)

        if frame_row is None:
            self.set_status_message(f"No frame found within 50ms of playhead ({playhead_time:.1f}ms)")
            return

        # Pre-fill dialog with existing frame data
        existing_color = {
            'r': int(frame_row.get('ch0_red', 0)),
            'g': int(frame_row.get('ch0_green', 0)),
            'b': int(frame_row.get('ch0_blue', 0))
        }
        existing_function = int(frame_row.get('ch0_function', 0))
        existing_marker = str(frame_row.get('marker', ''))

        dialog = ColorPickerDialog(self, prefill_color=existing_color, prefill_function=existing_function, prefill_marker=existing_marker)
        if dialog.exec():
            values = dialog.get_values()
            self.logic.update_frame(frame_time, values['color'], values['function'], values.get('marker'))

    def on_generate_breathing(self):
        params_config = [
            {'name': 'duration', 'label': 'Duration (ms)', 'type': 'float', 'default': 5000.0},
            {'name': 'interval', 'label': 'Interval (ms)', 'type': 'float', 'default': 100.0},
            {'name': 'color', 'label': 'Color', 'type': 'color', 'default': '#FFFFFF'},
            {'name': 'min_bright', 'label': 'Min Brightness', 'type': 'float', 'default': 0.1},
            {'name': 'max_bright', 'label': 'Max Brightness', 'type': 'float', 'default': 1.0},
        ]
        dialog = EffectDialog("Generate Breathing Effect", params_config, self)
        if dialog.exec():
            params = dialog.get_params()
            params['at_ms'] = self.edit_timeline.get_playback_head_time()
            self.generate_breathing_effect_requested.emit(params)

    def on_generate_rainbow(self):
        params_config = [
            {'name': 'duration', 'label': 'Duration (ms)', 'type': 'float', 'default': 10000.0},
            {'name': 'interval', 'label': 'Interval (ms)', 'type': 'float', 'default': 100.0},
            {'name': 'speed', 'label': 'Speed', 'type': 'float', 'default': 0.1},
        ]
        dialog = EffectDialog("Generate Rainbow Effect", params_config, self)
        if dialog.exec():
            params = dialog.get_params()
            params['at_ms'] = self.edit_timeline.get_playback_head_time()
            self.generate_rainbow_effect_requested.emit(params)

    def on_open_calibration(self):
        from ui.dialogs import CalibrationDialog
        current_gains = self.logic.get_current_calibration()
        dialog = CalibrationDialog(current_gains, self)
        if dialog.exec():
            r, g, b = dialog.get_values()
            self.logic.update_calibration(r, g, b)

    def on_fit_to_view(self):
        active_timeline = self.get_active_timeline()
        if not active_timeline: return

        # 获取播放头位置和选区范围
        playhead_time = active_timeline.get_playback_head_time()
        start, end = active_timeline.region_item.getRegion()

        # 判断播放头是否在选区内
        if start <= playhead_time <= end and abs(end - start) > 1:
            # Fit 选区
            padding = (end - start) * 0.05
            active_timeline.plot_item.setXRange(start - padding, end + padding, padding=0)
        else:
            # Fit 全局
            self.should_auto_zoom = True
            if active_timeline == self.source_timeline:
                current_data = self.logic.source_data_manager.get_full_data()
                self.source_timeline.set_data(current_data, auto_zoom=True)
            else:
                current_data = self.logic.data_manager.get_full_data()
                self.edit_timeline.set_data(current_data, auto_zoom=True)
            self.should_auto_zoom = False

    def on_show_offset_dialog(self):
        active_timeline = self.get_active_timeline()
        if active_timeline:
            active_timeline.show_offset_dialog()

    def on_apply_offset(self, offset_ms):
        active_timeline = self.get_active_timeline()
        if active_timeline:
            active_timeline.apply_quick_offset(offset_ms)

    def get_active_timeline(self):
        if self.source_timeline.underMouse():
            return self.source_timeline
        # Default to edit timeline for focus or if no timeline is under the mouse
        return self.edit_timeline

    def on_cut(self):
        active_timeline = self.get_active_timeline()
        if active_timeline == self.edit_timeline:
            start_ms, end_ms = active_timeline.get_selected_region()
            self.logic.cut_selection(start_ms, end_ms)
        else:
            self.set_status_message("Cut is not available on the source timeline.")

    def on_copy(self):
        active_timeline = self.get_active_timeline()
        start_ms, end_ms = active_timeline.get_selected_region()
        self.logic.copy_selection(start_ms, end_ms, active_timeline.timeline_type)

    def on_paste(self):
        active_timeline = self.get_active_timeline()
        if active_timeline == self.edit_timeline:
            self.logic.paste_selection(active_timeline.get_playback_head_time())
        else:
            self.set_status_message("Paste is not available on the source timeline.")

    def on_delete(self):
        active_timeline = self.get_active_timeline()
        if active_timeline == self.edit_timeline:
            start_ms, end_ms = active_timeline.get_selected_region()
            self.logic.delete_selection(start_ms, end_ms)
        else:
            self.set_status_message("Delete is not available on the source timeline.")

    def on_import_source_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Source Video",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm *.m4v)"
        )
        if file_path:
            self.source_preview_widget.load_video(file_path)
            self.logic.load_video_audio(file_path, 'source')
            self.set_status_message(f"Source video loaded: {os.path.basename(file_path)}")

    def on_import_edit_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Edit Video",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm *.m4v)"
        )
        if file_path:
            self.edit_preview_widget.load_video(file_path)
            self.logic.load_video_audio(file_path, 'edit')
            self.set_status_message(f"Edit video loaded: {os.path.basename(file_path)}")

    def on_toggle_sync_playback(self):
        # This would contain the logic to sync playback between timelines and video
        # For now, just show if it's enabled in the status bar
        if self.sync_playback_action.isChecked():
            self.set_status_message("Video playback synchronization enabled")
        else:
            self.set_status_message("Video playback synchronization disabled")

    def sync_source_video_to_timeline(self, time_ms: float):
        """Synchronize source video playback to timeline position"""
        if self.sync_playback_action.isChecked() and not self.syncing_source_video_to_timeline:
            try:
                self.syncing_source_video_to_timeline = True
                self.source_preview_widget.set_playback_position(int(time_ms))
            except Exception as e:
                self.set_status_message(f"Error syncing source video: {str(e)}")
            finally:
                self.syncing_source_video_to_timeline = False

    def sync_edit_video_to_timeline(self, time_ms: float):
        """Synchronize edit video playback to timeline position"""
        if self.sync_playback_action.isChecked() and not self.syncing_edit_video_to_timeline:
            try:
                self.syncing_edit_video_to_timeline = True
                self.edit_preview_widget.set_playback_position(int(time_ms))
            except Exception as e:
                self.set_status_message(f"Error syncing edit video: {str(e)}")
            finally:
                self.syncing_edit_video_to_timeline = False

    def sync_timeline_to_source_video(self, time_ms: float):
        """Synchronize source timeline playback head to video position"""
        if self.sync_playback_action.isChecked() and not self.syncing_timeline_to_source_video:
            try:
                self.syncing_timeline_to_source_video = True
                self.source_timeline.playback_head.blockSignals(True)
                self.source_timeline_group.set_playback_head_time(time_ms)
                self.source_timeline.playback_head.blockSignals(False)
            except Exception as e:
                self.set_status_message(f"Error syncing source timeline: {str(e)}")
            finally:
                self.syncing_timeline_to_source_video = False

    def sync_timeline_to_edit_video(self, time_ms: float):
        """Synchronize edit timeline playback head to video position"""
        if self.sync_playback_action.isChecked() and not self.syncing_timeline_to_edit_video:
            try:
                self.syncing_timeline_to_edit_video = True
                self.edit_timeline.playback_head.blockSignals(True)
                self.edit_timeline_group.set_playback_head_time(time_ms)
                self.edit_timeline.playback_head.blockSignals(False)
            except Exception as e:
                self.set_status_message(f"Error syncing edit timeline: {str(e)}")
            finally:
                self.syncing_timeline_to_edit_video = False

    def on_source_timeline_playback_head_changed(self):
        """Handle when the source timeline playback head is manually moved (e.g. by dragging)"""
        current_time = self.source_timeline.get_playback_head_time()
        self.sync_source_video_to_timeline(current_time)

    def on_edit_timeline_playback_head_changed(self):
        """Handle when the edit timeline playback head is manually moved (e.g. by dragging)"""
        current_time = self.edit_timeline.get_playback_head_time()
        self.sync_edit_video_to_timeline(current_time)

    def on_source_region_selected(self, start_ms: float, end_ms: float):
        has_selection = abs(end_ms - start_ms) > 1
        if has_selection:
            self.data_table.set_data(self.logic.source_data_manager.get_segment(start_ms, end_ms))
        else:
            self.data_table.set_data(pd.DataFrame())

    def on_edit_region_selected(self, start_ms: float, end_ms: float):
        has_selection = abs(end_ms - start_ms) > 1
        if has_selection:
            self.data_table.set_data(self.logic.data_manager.get_segment(start_ms, end_ms))
        else:
            self.data_table.set_data(pd.DataFrame())

    def closeEvent(self, event):
        self.edit_timeline.shutdown()
        self.source_timeline.shutdown()
        event.accept()

    # --- Public Slots for Logic Controller ---

    @Slot(pd.DataFrame)
    def on_timeline_data_changed(self, df):
        auto_zoom = self.should_auto_zoom and (self.is_initial_load or df.empty)
        self.edit_timeline.set_data(df, auto_zoom=auto_zoom)
        self.data_table.set_data(df)
        if self.is_initial_load and not df.empty:
            self.is_initial_load = False
            self.should_auto_zoom = False

    @Slot(pd.DataFrame)
    def on_source_data_changed(self, df):
        self.source_timeline.set_data(df, auto_zoom=True)

    @Slot(str)
    def set_status_message(self, message):
        self.status_bar.showMessage(message, 3000) # Show for 3 seconds

    @Slot(bool)
    def set_undo_enabled(self, enabled):
        self.undo_action.setEnabled(enabled)

    @Slot(bool)
    def set_redo_enabled(self, enabled):
        self.redo_action.setEnabled(enabled)

    @Slot(float, float)
    def on_offset_applied(self, new_start_ms, new_end_ms):
        self.edit_timeline.set_selected_region(new_start_ms, new_end_ms)

    @Slot(str)
    def set_theme(self, theme_name):
        try:
            # This makes path resolution more robust
            base_path = os.path.dirname(os.path.abspath(__file__))
            style_path = os.path.join(base_path, "..", "resources", "styles", f"{theme_name}.qss")
            with open(style_path, "r") as f:
                style_sheet = f.read()
                QApplication.instance().setStyleSheet(style_sheet)
        except FileNotFoundError:
            self.set_status_message(f"Error: Stylesheet '{theme_name}.qss' not found.")

    def closeEvent(self, event):
        # Save window geometry and state per PRD 2.3
        settings = QSettings("LumaFlow", "LumaFlow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

        # Shutdown app logic (audio manager and device worker)
        try:
            if hasattr(self, 'logic'):
                self.logic.shutdown()
        except:
            pass

        # Shutdown video player widgets
        try:
            if hasattr(self, 'source_preview_widget') and self.source_preview_widget.media_player:
                self.source_preview_widget.media_player.stop()
        except:
            pass

        try:
            if hasattr(self, 'edit_preview_widget') and self.edit_preview_widget.media_player:
                self.edit_preview_widget.media_player.stop()
        except:
            pass

        # Shutdown timeline groups
        try:
            self.edit_timeline_group.shutdown()
            self.source_timeline_group.shutdown()
        except:
            pass

        super().closeEvent(event)

    def _restore_window_state(self):
        """Restore window geometry and dock positions from QSettings per PRD 2.3"""
        settings = QSettings("LumaFlow", "LumaFlow")
        geometry = settings.value("geometry")
        window_state = settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        if window_state:
            self.restoreState(window_state)

    # --- Audio Control Handlers ---
    def _on_source_audio_visibility_changed(self, timeline_type: str, visible: bool):
        self.source_timeline_group.show_audio_track(visible)

    def _on_edit_audio_visibility_changed(self, timeline_type: str, visible: bool):
        self.edit_timeline_group.show_audio_track(visible)

    def _on_source_audio_height_changed(self, timeline_type: str, height: float):
        self.source_timeline_group.set_audio_height(height)

    def _on_edit_audio_height_changed(self, timeline_type: str, height: float):
        self.edit_timeline_group.set_audio_height(height)

    def _on_source_audio_channel_changed(self, timeline_type: str, mode: str):
        if self.logic.current_source_video_path:
            self.logic.change_audio_channel_mode(timeline_type, self.logic.current_source_video_path, mode)

    def _on_edit_audio_channel_changed(self, timeline_type: str, mode: str):
        if self.logic.current_edit_video_path:
            self.logic.change_audio_channel_mode(timeline_type, self.logic.current_edit_video_path, mode)

    def _on_source_audio_colormap_changed(self, timeline_type: str, colormap: str):
        self.source_timeline_group.set_colormap(colormap)

    def _on_edit_audio_colormap_changed(self, timeline_type: str, colormap: str):
        self.edit_timeline_group.set_colormap(colormap)

    def _on_source_audio_params_changed(self, timeline_type: str, params: dict):
        """Handle processing parameters change"""
        if self.logic.current_source_video_path:
            # Update default params
            self.logic.audio_manager.update_params(params)
            # Trigger reprocessing
            reply = QMessageBox.question(
                self,
                "重新处理音频",
                "更改频率范围需要重新处理音频，这可能需要一些时间。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                # 获取当前声道模式
                mode = self.source_audio_controls.channel_combo.currentText()
                mode_map = {
                    "单声道": "mono",
                    "立体声": "stereo",
                    "左声道": "left",
                    "右声道": "right"
                }
                mode_code = mode_map.get(mode, "stereo")
                self.logic.audio_manager.extract_audio(self.logic.current_source_video_path, mode_code)

    def _on_edit_audio_params_changed(self, timeline_type: str, params: dict):
        """Handle processing parameters change"""
        if self.logic.current_edit_video_path:
            # Update default params
            self.logic.audio_manager.update_params(params)
            # Trigger reprocessing
            reply = QMessageBox.question(
                self,
                "重新处理音频",
                "更改频率范围需要重新处理音频，这可能需要一些时间。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                # 获取当前声道模式
                mode = self.edit_audio_controls.channel_combo.currentText()
                mode_map = {
                    "单声道": "mono",
                    "立体声": "stereo",
                    "左声道": "left",
                    "右声道": "right"
                }
                mode_code = mode_map.get(mode, "stereo")
                self.logic.audio_manager.extract_audio(self.logic.current_edit_video_path, mode_code)

    def _on_source_audio_data_ready(self, audio_data):
        self.source_audio_controls.clear_progress()
        self.source_timeline_group.set_audio_data(audio_data)
        duration_sec = audio_data.duration_ms / 1000.0
        info = f"音频已加载 ({audio_data.sample_rate}Hz, {duration_sec:.1f}s)"
        self.source_audio_controls.set_audio_loaded(True, info)

    def _on_edit_audio_data_ready(self, audio_data):
        self.edit_audio_controls.clear_progress()
        self.edit_timeline_group.set_audio_data(audio_data)
        duration_sec = audio_data.duration_ms / 1000.0
        info = f"音频已加载 ({audio_data.sample_rate}Hz, {duration_sec:.1f}s)"
        self.edit_audio_controls.set_audio_loaded(True, info)

    def _on_audio_processing_failed(self, timeline_type: str, error: str):
        if timeline_type == 'source':
            self.source_audio_controls.clear_progress()
            self.source_audio_controls.set_error(error)
        else:
            self.edit_audio_controls.clear_progress()
            self.edit_audio_controls.set_error(error)

    def _on_audio_progress(self, timeline_type: str, stage: str, percentage: int):
        """Handle audio processing progress updates"""
        if timeline_type == 'source':
            self.source_audio_controls.set_progress(stage, percentage)
        else:
            self.edit_audio_controls.set_progress(stage, percentage)

    def on_open_audio_settings(self):
        """Open the audio settings dialog"""
        if self.audio_settings_dialog is None:
            self.audio_settings_dialog = AudioSettingsDialog(self, self)
        self.audio_settings_dialog.show()
        self.audio_settings_dialog.raise_()
        self.audio_settings_dialog.activateWindow()

    # --- 播放互斥控制 ---
    def _on_source_playback_started(self):
        """当源播放器开始播放时，暂停编辑播放器"""
        self.edit_preview_widget.pause()

    def _on_edit_playback_started(self):
        """当编辑播放器开始播放时，暂停源播放器"""
        self.source_preview_widget.pause()

    # --- Device Output Controls ---
    def _connect_device_output_signals(self):
        """Connect device output panel signals to logic."""
        serial_panel = self.device_output_widget.serial_panel
        keyboard_panel = self.device_output_widget.keyboard_panel

        # Serial panel signals
        serial_panel.refresh_requested.connect(self._refresh_serial_ports)
        serial_panel.connect_requested.connect(self.logic.connect_serial)
        serial_panel.disconnect_requested.connect(self.logic.disconnect_serial)
        serial_panel.offset_changed.connect(self.logic.set_serial_offset)

        # Keyboard panel signals
        keyboard_panel.connect_requested.connect(self.logic.connect_keyboard)
        keyboard_panel.disconnect_requested.connect(self.logic.disconnect_keyboard)
        keyboard_panel.offset_changed.connect(self.logic.set_keyboard_offset)
        keyboard_panel.target_keyboard_changed.connect(self.logic.set_keyboard_target_keyboard)
        keyboard_panel.target_lightstrip_changed.connect(self.logic.set_keyboard_target_lightstrip)
        keyboard_panel.channel_changed.connect(self.logic.set_keyboard_channel)
        keyboard_panel.device_path_changed.connect(self.logic.set_keyboard_device_path)

        # Set default device path
        keyboard_panel.set_device_path(self.logic.keyboard_device.DEFAULT_DEVICE_PATH)

        # Initial port list
        self._refresh_serial_ports()

    def on_about(self):
        QMessageBox.about(
            self,
            "About LumaFlow",
            """<h3>LumaFlow</h3>
            <p>Version 1.0</p>
            <p>Author: Ltyridium <a href="https://space.bilibili.com/38596041"> B站主页</a></p>
            <p>GitHub: <a href="https://github.com/ltyridium/LumaFlow">https://github.com/ltyridium/LumaFlow</a></p>
            <p><a href="https://space.bilibili.com/36081646">关注洛天依谢谢喵</a></p>
            """
        )

    def _refresh_serial_ports(self):
        """Refresh the list of available serial ports."""
        ports = self.logic.get_serial_ports()
        self.device_output_widget.serial_panel.update_ports(ports)

    # --- 键盘事件处理 ---
    def keyPressEvent(self, event):
        """处理主窗口的键盘事件"""
        # 空格键：切换当前活动时间轴对应的视频播放
        if event.key() == Qt.Key_Space:
            # 检查哪个时间轴有焦点
            if self.source_timeline.hasFocus() or self.source_audio_track.hasFocus():
                self.source_preview_widget.toggle_playback()
                event.accept()
                return
            elif self.edit_timeline.hasFocus() or self.edit_audio_track.hasFocus():
                self.edit_preview_widget.toggle_playback()
                event.accept()
                return
        super().keyPressEvent(event)