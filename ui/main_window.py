import sys
import os
import pandas as pd
from PySide6.QtCore import Signal, Slot, Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QMessageBox, QInputDialog, QSplitter,
    QStyle, QToolBar, QDockWidget, QLabel, QProgressBar
)

# Assuming these are in the correct project structure
from .timeline_group_widget import TimelineGroupWidget
from .widgets import DataTableWidget
from .dialogs import EffectDialog, ColorPickerDialog
from .audio_controls_widget import AudioControlsWidget
from .audio_settings_dialog import AudioSettingsDialog
from .video_player_widget import VideoPlayerWidget
from .device_output_dock import DeviceOutputWidget
from core.i18n import get_language, set_language, tr
from core.resource_paths import icon_path, resource_path
from core.timecode import format_time_ms, parse_timecode


DEFAULT_NEW_EDIT_DURATION_SEC = 9600.0
AUTO_ROLL_THRESHOLD_RATIO = 0.85
AUTO_ROLL_PAGE_RATIO = 0.75

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
    generate_gradient_effect_requested = Signal(dict)
    generate_intermediate_frames_requested = Signal(dict)

    def __init__(self, app_logic, parent=None):
        super().__init__(parent)
        self.logic = app_logic
        self.current_language = get_language()
        self.setWindowTitle(tr("app.title"))
        app_icon_path = icon_path()
        if app_icon_path.exists():
            self.setWindowIcon(QIcon(str(app_icon_path)))
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
        self.source_dock = QDockWidget(tr("dock.source_monitor"), self)
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
        self.data_table_dock = QDockWidget(tr("dock.data_table"), self)
        self.data_table_dock.setObjectName("DataTableDock")
        self.data_table = DataTableWidget()
        self.data_table_dock.setWidget(self.data_table)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.data_table_dock)

        # --- Left Top Dock: Source Preview (Video) ---
        self.source_preview_dock = QDockWidget(tr("dock.source_preview"), self)
        self.source_preview_dock.setObjectName("SourcePreviewDock")
        self.source_preview_widget = VideoPlayerWidget()
        self.source_preview_dock.setWidget(self.source_preview_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.source_preview_dock)
        self.source_preview_dock.hide()  # 默认隐藏 source 预览

        # --- Left Bottom Dock: Program Preview (Video) ---
        self.edit_preview_dock = QDockWidget(tr("dock.program_preview"), self)
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
        self.device_output_dock = QDockWidget(tr("dock.device_output"), self)
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

        # Add progress bar for audio processing
        self.audio_progress_label = QLabel("")
        self.audio_progress_bar = QProgressBar()
        self.audio_progress_bar.setMaximum(100)
        self.audio_progress_bar.setFixedWidth(200)
        self.audio_progress_bar.setVisible(False)

        self.status_bar.addPermanentWidget(self.audio_progress_label)
        self.status_bar.addPermanentWidget(self.audio_progress_bar)
        self.status_bar.showMessage(tr("app.ready"))

        # Apply dark theme by default on startup
        QTimer.singleShot(0, lambda: self.set_theme("dark_theme"))

        # Restore window state if available
        self._restore_window_state()

    # [MODIFIED] The toolbar is now the primary hub for common actions.
    def create_tool_bar(self):
        """Creates and configures the main application toolbar with logical groupings."""
        tool_bar = QToolBar(tr("toolbar.main"))
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
        tool_bar.addAction(self.auto_roll_action)

        return tool_bar

    # [MODIFIED] Added more standard icons to actions for a richer toolbar experience.
    def create_actions(self):
        self.new_edit_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), tr("action.new_edit"), self)
        self.new_edit_action.setShortcut(QKeySequence.New)
        self.open_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), tr("action.open_edit"), self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_source_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), tr("action.open_source"), self)
        self.save_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), tr("action.save"), self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action = QAction(tr("action.save_as"), self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.exit_action = QAction(tr("action.exit"), self)
        self.exit_action.setShortcut(QKeySequence.Quit)

        self.undo_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft), tr("action.undo"), self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight), tr("action.redo"), self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.cut_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton), tr("action.cut"), self)
        self.cut_action.setShortcut(QKeySequence.Cut)
        self.copy_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon), tr("action.copy"), self)
        self.copy_action.setShortcut(QKeySequence.Copy)
        self.paste_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), tr("action.paste"), self)
        self.paste_action.setShortcut(QKeySequence.Paste)
        self.delete_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), tr("action.delete"), self)
        self.delete_action.setShortcut(QKeySequence.Delete)

        self.dark_theme_action = QAction(tr("action.dark_theme"), self)
        self.light_theme_action = QAction(tr("action.light_theme"), self)
        self.calibration_action = QAction(tr("action.rgb_calibration"), self)
        self.fit_view_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), tr("action.fit_selection"), self)
        self.fit_view_action.setShortcut("F")

        self.add_marker_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), tr("action.add_marker"), self)
        self.add_marker_action.setShortcut("M")
        self.insert_blackout_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), tr("action.insert_blackout"), self)
        self.insert_blackout_action.setShortcut("B")
        self.insert_color_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton), tr("action.insert_color"), self)
        self.insert_color_action.setShortcut("I")
        self.edit_frame_action = QAction(tr("action.edit_frame"), self)
        self.edit_frame_action.setShortcut("E")

        self.generate_breathing_action = QAction(tr("action.generate_breathing"), self)
        self.generate_rainbow_action = QAction(tr("action.generate_rainbow"), self)
        self.generate_gradient_action = QAction(tr("action.generate_gradient"), self)

        self.offset_dialog_action = QAction(tr("action.specify_offset"), self)
        self.offset_dialog_action.setShortcut("Shift+M")
        self.offset_left_action = QAction(tr("action.offset_left"), self)
        self.offset_left_action.setShortcut("Ctrl+[")
        self.offset_right_action = QAction(tr("action.offset_right"), self)
        self.offset_right_action.setShortcut("Ctrl+]")
        self.go_to_time_action = QAction(tr("action.go_to_time"), self)
        self.go_to_time_action.setShortcut("Ctrl+G")

        self.import_source_video_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            tr("action.import_source_video"),
            self,
        )
        self.import_edit_video_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            tr("action.import_edit_video"),
            self,
        )
        self.sync_playback_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            tr("action.sync_playback"),
            self,
        )
        self.sync_playback_action.setCheckable(True)
        self.sync_playback_action.setChecked(True)
        self.auto_roll_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            tr("action.auto_roll"),
            self,
        )
        self.auto_roll_action.setCheckable(True)
        self.auto_roll_action.setChecked(False)

        self.about_action = QAction(tr("action.about"), self)
        self.about_action.triggered.connect(self.on_about)

        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        self.language_zh_cn_action = QAction(tr("language.zh-CN"), self, checkable=True)
        self.language_en_us_action = QAction(tr("language.en-US"), self, checkable=True)
        self.language_action_group.addAction(self.language_zh_cn_action)
        self.language_action_group.addAction(self.language_en_us_action)
        (self.language_zh_cn_action if self.current_language == "zh-CN" else self.language_en_us_action).setChecked(True)

    def create_menus(self):
        # File menu
        file_menu = self.menuBar().addMenu(tr("menu.file"))
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
        edit_menu = self.menuBar().addMenu(tr("menu.edit"))
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)

        # View menu - Per PRD 2.3: Toggle actions for all Docks
        view_menu = self.menuBar().addMenu(tr("menu.view"))
        view_menu.addAction(self.dark_theme_action)
        view_menu.addAction(self.light_theme_action)
        view_menu.addSeparator()
        view_menu.addAction(self.calibration_action)
        view_menu.addAction(self.fit_view_action)
        view_menu.addSeparator()

        language_menu = view_menu.addMenu(tr("menu.language"))
        language_menu.addAction(self.language_zh_cn_action)
        language_menu.addAction(self.language_en_us_action)
        view_menu.addSeparator()

        # Dock toggle actions
        view_menu.addAction(self.source_dock.toggleViewAction())
        view_menu.addAction(self.data_table_dock.toggleViewAction())
        view_menu.addAction(self.source_preview_dock.toggleViewAction())
        view_menu.addAction(self.edit_preview_dock.toggleViewAction())
        view_menu.addAction(self.device_output_dock.toggleViewAction())

        # Timeline menu
        timeline_menu = self.menuBar().addMenu(tr("menu.timeline"))
        timeline_menu.addAction(self.add_marker_action)
        timeline_menu.addAction(self.edit_frame_action)  # Per PRD 5.1
        insert_menu = timeline_menu.addMenu(tr("menu.insert"))
        insert_menu.addAction(self.insert_blackout_action)
        insert_menu.addAction(self.insert_color_action)
        generate_menu = timeline_menu.addMenu(tr("menu.generate"))
        generate_menu.addAction(self.generate_breathing_action)
        generate_menu.addAction(self.generate_rainbow_action)
        generate_menu.addAction(self.generate_gradient_action)
        timeline_menu.addSeparator()
        offset_menu = timeline_menu.addMenu(tr("menu.offset"))
        offset_menu.addAction(self.offset_dialog_action)
        offset_menu.addAction(self.offset_left_action)
        offset_menu.addAction(self.offset_right_action)
        timeline_menu.addAction(self.go_to_time_action)

        # Audio menu
        audio_menu = self.menuBar().addMenu(tr("menu.audio"))
        self.audio_settings_action = QAction(tr("action.audio_visualization_settings"), self)
        audio_menu.addAction(self.audio_settings_action)

        # Help menu
        help_menu = self.menuBar().addMenu(tr("menu.help"))
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
        self.generate_gradient_action.triggered.connect(self.on_generate_gradient)

        self.offset_dialog_action.triggered.connect(self.on_show_offset_dialog)
        self.offset_left_action.triggered.connect(lambda: self.on_apply_offset(-100))
        self.offset_right_action.triggered.connect(lambda: self.on_apply_offset(100))
        self.go_to_time_action.triggered.connect(self.on_go_to_time)

        # Video import and sync actions
        self.import_source_video_action.triggered.connect(self.on_import_source_video)
        self.import_edit_video_action.triggered.connect(self.on_import_edit_video)
        self.sync_playback_action.triggered.connect(self.on_toggle_sync_playback)
        self.auto_roll_action.triggered.connect(self.on_toggle_auto_roll)

        # Audio settings action
        self.audio_settings_action.triggered.connect(self.on_open_audio_settings)
        self.language_zh_cn_action.triggered.connect(lambda: self.on_change_language("zh-CN"))
        self.language_en_us_action.triggered.connect(lambda: self.on_change_language("en-US"))

        # Timeline group signals
        self.edit_timeline_group.region_selected.connect(self.on_edit_region_selected)
        self.source_timeline_group.region_selected.connect(self.on_source_region_selected)

        # Audio control connections
        self.source_audio_controls.visibility_changed.connect(self._on_source_audio_visibility_changed)
        self.edit_audio_controls.visibility_changed.connect(self._on_edit_audio_visibility_changed)
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
        self.logic.serial_frame_sent.connect(
            self.device_output_widget.serial_panel.update_frames_sent
        )
        self.logic.serial_auth_status_changed.connect(
            self.device_output_widget.serial_panel.set_auth_status
        )
        self.logic.serial_auth_lic_info_changed.connect(
            self.device_output_widget.serial_panel.set_lic_info
        )
        self.device_output_widget.serial_panel.set_lic_info(self.logic.get_serial_auth_lic_info())

        # Connect UI requests to the logic controller
        self.add_marker_requested.connect(self.logic.add_marker)
        self.insert_blackout_requested.connect(self.logic.insert_blackout_frame)
        self.insert_color_frame_requested.connect(self.logic.insert_color_frame)
        self.generate_breathing_effect_requested.connect(self.logic.generate_breathing_effect)
        self.generate_rainbow_effect_requested.connect(self.logic.generate_rainbow_effect)
        self.generate_gradient_effect_requested.connect(self.logic.generate_gradient_effect)
        self.generate_intermediate_frames_requested.connect(self.logic.generate_intermediate_frames)

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
        file_path, _ = QFileDialog.getOpenFileName(self, tr("action.open_edit"), "", tr("main.file_filter_edit"))
        if file_path:
            self.open_requested.emit(file_path)

    def on_open_source_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("action.open_source"), "", tr("main.file_filter_edit"))
        if file_path:
            self.open_source_requested.emit(file_path)

    def on_save_as_clicked(self):
        file_path, _ = QFileDialog.getSaveFileName(self, tr("main.save_as_title"), "", tr("main.file_filter_edit"))
        if file_path:
            self.save_requested.emit(file_path)

    def on_new_edit(self):
        default_duration_sec = self._get_default_new_edit_duration_sec()
        duration_sec, ok = QInputDialog.getDouble(
            self,
            tr("main.new_edit_title"),
            tr("main.new_edit_label"),
            default_duration_sec,
            1.0,
            10000.0,
            2,
        )
        if ok and duration_sec > 0:
            self.new_edit_requested.emit(duration_sec)

    def _get_default_new_edit_duration_sec(self) -> float:
        """Choose the best default duration for a new edit project."""
        duration_candidates = (
            self.edit_preview_widget.get_media_duration(),
            self.logic.edit_audio_duration_ms,
            self.source_preview_widget.get_media_duration(),
            self.logic.source_audio_duration_ms,
        )

        for duration_ms in duration_candidates:
            if duration_ms and duration_ms > 0:
                duration_sec = duration_ms / 1000.0
                return min(max(duration_sec, 1.0), 10000.0)

        return DEFAULT_NEW_EDIT_DURATION_SEC

    def on_add_marker(self):
        active_timeline = self.get_active_timeline()
        if not active_timeline: return
        name, ok = QInputDialog.getText(self, tr("action.add_marker"), tr("dialog.color_frame.marker"))
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
            self.set_status_message(tr("status.edit_frame_only_edit_timeline"))
            return

        playhead_time = self.edit_timeline.get_playback_head_time()
        frame_row, frame_time = self.edit_timeline.get_frame_at_time(playhead_time, tolerance_ms=50.0)

        if frame_row is None:
            self.set_status_message(tr("status.no_frame_near_playhead", time=playhead_time))
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
            {'name': 'duration', 'label': tr('dialog.gradient.duration'), 'type': 'float', 'default': 5000.0},
            {'name': 'interval', 'label': tr('dialog.gradient.interval'), 'type': 'float', 'default': 100.0},
            {'name': 'color', 'label': tr('dialog.color_frame.group_color'), 'type': 'color', 'default': '#FFFFFF'},
            {'name': 'min_bright', 'label': tr('dialog.effect.min_brightness'), 'type': 'float', 'default': 0.1},
            {'name': 'max_bright', 'label': tr('dialog.effect.max_brightness'), 'type': 'float', 'default': 1.0},
        ]
        dialog = EffectDialog(tr("action.generate_breathing"), params_config, self)
        if dialog.exec():
            params = dialog.get_params()
            params['at_ms'] = self.edit_timeline.get_playback_head_time()
            self.generate_breathing_effect_requested.emit(params)

    def on_generate_rainbow(self):
        params_config = [
            {'name': 'duration', 'label': tr('dialog.gradient.duration'), 'type': 'float', 'default': 10000.0},
            {'name': 'interval', 'label': tr('dialog.gradient.interval'), 'type': 'float', 'default': 100.0},
            {'name': 'speed', 'label': tr('dialog.effect.speed'), 'type': 'float', 'default': 0.1},
        ]
        dialog = EffectDialog(tr("action.generate_rainbow"), params_config, self)
        if dialog.exec():
            params = dialog.get_params()
            params['at_ms'] = self.edit_timeline.get_playback_head_time()
            self.generate_rainbow_effect_requested.emit(params)

    def on_generate_gradient(self):
        from ui.dialogs import GradientDialog
        start_ms, end_ms = self.edit_timeline.get_selected_region()
        if abs(end_ms - start_ms) <= 1:
            self.set_status_message(tr("status.no_region_selected"))
            return

        dialog = GradientDialog(self, start_ms, end_ms, self.logic.data_manager)
        if dialog.exec():
            params = dialog.get_params()
            params['at_ms'] = start_ms
            self.generate_gradient_effect_requested.emit(params)

    def on_generate_intermediate_frames(self):
        start_ms, end_ms = self.edit_timeline.get_selected_region()
        if abs(end_ms - start_ms) <= 1:
            self.set_status_message(tr("status.generate_intermediate_requires_region"))
            return

        anchor_df = self.logic.data_manager.get_segment(start_ms, end_ms)
        if len(anchor_df) < 2:
            self.set_status_message(tr("status.generate_intermediate_requires_two_frames"))
            return

        params_config = [
            {
                'name': 'interval',
                'label': tr('dialog.intermediate.interval'),
                'type': 'float',
                'default': 200.0,
                'min': 1.0,
            },
        ]
        dialog = EffectDialog(tr("action.generate_intermediate_frames"), params_config, self)
        if dialog.exec():
            params = dialog.get_params()
            params['start_ms'] = start_ms
            params['end_ms'] = end_ms
            self.generate_intermediate_frames_requested.emit(params)

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

        start, end = active_timeline.region_item.getRegion()

        if abs(end - start) > 1:
            padding = (end - start) * 0.05
            active_timeline.set_view_range_clamped(start - padding, end + padding)
        else:
            self.set_status_message(tr("status.fit_selection_requires_region"))

    def fit_active_timeline_to_all(self):
        active_timeline = self.get_active_timeline()
        if not active_timeline:
            return

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
            self.set_status_message(tr("status.cut_not_available_source"))

    def on_copy(self):
        active_timeline = self.get_active_timeline()
        start_ms, end_ms = active_timeline.get_selected_region()
        self.logic.copy_selection(start_ms, end_ms, active_timeline.timeline_type)

    def on_paste(self):
        active_timeline = self.get_active_timeline()
        if active_timeline == self.edit_timeline:
            self.logic.paste_selection(active_timeline.get_playback_head_time())
        else:
            self.set_status_message(tr("status.paste_not_available_source"))

    def on_delete(self):
        active_timeline = self.get_active_timeline()
        if active_timeline == self.edit_timeline:
            start_ms, end_ms = active_timeline.get_selected_region()
            self.logic.delete_selection(start_ms, end_ms)
        else:
            self.set_status_message(tr("status.delete_not_available_source"))

    def on_import_source_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("main.import_source_video"),
            "",
            tr("main.file_filter_video")
        )
        if file_path:
            self.source_preview_widget.load_video(file_path)
            self.logic.load_video_audio(file_path, 'source')
            self.set_status_message(tr("status.source_video_loaded", name=os.path.basename(file_path)))

    def on_import_edit_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("main.import_edit_video"),
            "",
            tr("main.file_filter_video")
        )
        if file_path:
            self.edit_preview_widget.load_video(file_path)
            self.logic.load_video_audio(file_path, 'edit')
            self.set_status_message(tr("status.edit_video_loaded", name=os.path.basename(file_path)))

    def on_toggle_sync_playback(self):
        # This would contain the logic to sync playback between timelines and video
        # For now, just show if it's enabled in the status bar
        if self.sync_playback_action.isChecked():
            self.set_status_message(tr("status.sync_enabled"))
        else:
            self.set_status_message(tr("status.sync_disabled"))

    def on_toggle_auto_roll(self):
        if self.auto_roll_action.isChecked():
            self.set_status_message(tr("status.auto_roll_enabled"))
        else:
            self.set_status_message(tr("status.auto_roll_disabled"))

    def on_go_to_time(self):
        preview_widget = self._get_preview_widget_for_timeline_action(default_to_edit=True)
        if preview_widget is None or preview_widget.get_media_duration() <= 0:
            self.set_status_message(tr("status.go_to_time_requires_video"))
            return

        current_position = preview_widget.get_current_position()
        text, ok = QInputDialog.getText(
            self,
            tr("dialog.go_to_time.title"),
            tr("dialog.go_to_time.label"),
            text=format_time_ms(current_position),
        )
        if not ok:
            return

        try:
            requested_time_ms = parse_timecode(text)
        except ValueError:
            QMessageBox.warning(
                self,
                tr("dialog.go_to_time.invalid_title"),
                tr("dialog.go_to_time.invalid_message"),
            )
            return

        actual_time_ms = preview_widget.seek_to_time(requested_time_ms)
        if actual_time_ms is not None:
            self.set_status_message(
                tr("status.go_to_time_applied", time=format_time_ms(actual_time_ms))
            )

    def sync_source_video_to_timeline(self, time_ms: float):
        """Synchronize source video playback to timeline position"""
        if self.sync_playback_action.isChecked() and not self.syncing_source_video_to_timeline:
            try:
                self.syncing_source_video_to_timeline = True
                self.source_preview_widget.set_playback_position(int(time_ms))
            except Exception as e:
                self.set_status_message(tr("status.sync_source_video_error", error=str(e)))
            finally:
                self.syncing_source_video_to_timeline = False

    def sync_edit_video_to_timeline(self, time_ms: float):
        """Synchronize edit video playback to timeline position"""
        if self.sync_playback_action.isChecked() and not self.syncing_edit_video_to_timeline:
            try:
                self.syncing_edit_video_to_timeline = True
                self.edit_preview_widget.set_playback_position(int(time_ms))
            except Exception as e:
                self.set_status_message(tr("status.sync_edit_video_error", error=str(e)))
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
                self._maybe_auto_roll_timeline(self.source_timeline_group, time_ms)
            except Exception as e:
                self.set_status_message(tr("status.sync_source_timeline_error", error=str(e)))
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
                self._maybe_auto_roll_timeline(self.edit_timeline_group, time_ms)
            except Exception as e:
                self.set_status_message(tr("status.sync_edit_timeline_error", error=str(e)))
            finally:
                self.syncing_timeline_to_edit_video = False

    def _maybe_auto_roll_timeline(self, timeline_group, time_ms: float):
        if not self.auto_roll_action.isChecked():
            return

        timeline = timeline_group.timeline
        x_min, x_max = timeline.plot_item.viewRange()[0]
        view_width = x_max - x_min
        if view_width <= 0:
            return

        limit_ms = timeline._get_timeline_limit_ms()
        if limit_ms is None or view_width >= limit_ms:
            return

        trigger_x = x_min + view_width * AUTO_ROLL_THRESHOLD_RATIO
        if time_ms < trigger_x:
            return

        new_start = x_min + view_width * AUTO_ROLL_PAGE_RATIO
        new_end = new_start + view_width
        timeline.set_view_range_clamped(new_start, new_end)

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
            style_path = resource_path("styles", f"{theme_name}.qss")
            with style_path.open("r", encoding="utf-8") as f:
                style_sheet = f.read()
                QApplication.instance().setStyleSheet(style_sheet)
        except FileNotFoundError:
            self.set_status_message(tr("status.stylesheet_not_found", name=theme_name))

    def closeEvent(self, event):
        # Save window geometry and state per PRD 2.3
        settings = QSettings("LumaFlow", "LumaFlow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("view/auto_roll", self.auto_roll_action.isChecked())

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
        auto_roll_enabled = settings.value("view/auto_roll", False, bool)
        if geometry:
            self.restoreGeometry(geometry)
        if window_state:
            self.restoreState(window_state)
        self.auto_roll_action.setChecked(auto_roll_enabled)

    # --- Audio Control Handlers ---
    def _on_source_audio_visibility_changed(self, timeline_type: str, visible: bool):
        self.source_timeline_group.show_audio_track(visible)

    def _on_edit_audio_visibility_changed(self, timeline_type: str, visible: bool):
        self.edit_timeline_group.show_audio_track(visible)

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
                tr("audio_settings.reprocess_title"),
                tr("audio_settings.reprocess_message"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                mode_code = self.source_audio_controls.channel_combo.currentData() or "stereo"
                self.logic.audio_manager.extract_audio(self.logic.current_source_video_path, mode_code)

    def _on_edit_audio_params_changed(self, timeline_type: str, params: dict):
        """Handle processing parameters change"""
        if self.logic.current_edit_video_path:
            # Update default params
            self.logic.audio_manager.update_params(params)
            # Trigger reprocessing
            reply = QMessageBox.question(
                self,
                tr("audio_settings.reprocess_title"),
                tr("audio_settings.reprocess_message"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                mode_code = self.edit_audio_controls.channel_combo.currentData() or "stereo"
                self.logic.audio_manager.extract_audio(self.logic.current_edit_video_path, mode_code)

    def _on_source_audio_data_ready(self, audio_data):
        # Hide progress bar after completion
        self.audio_progress_bar.setVisible(False)
        self.audio_progress_label.setText("")

        self.source_audio_controls.clear_progress()
        self.source_timeline_group.set_audio_data(audio_data)
        duration_sec = audio_data.duration_ms / 1000.0
        info = tr("audio_controls.loaded_with_info", sample_rate=audio_data.sample_rate, duration=duration_sec)
        self.source_audio_controls.set_audio_loaded(True, info)

    def _on_edit_audio_data_ready(self, audio_data):
        # Hide progress bar after completion
        self.audio_progress_bar.setVisible(False)
        self.audio_progress_label.setText("")

        self.edit_audio_controls.clear_progress()
        self.edit_timeline_group.set_audio_data(audio_data)
        duration_sec = audio_data.duration_ms / 1000.0
        info = tr("audio_controls.loaded_with_info", sample_rate=audio_data.sample_rate, duration=duration_sec)
        self.edit_audio_controls.set_audio_loaded(True, info)

    def _on_audio_processing_failed(self, timeline_type: str, error: str):
        # Hide progress bar on error
        self.audio_progress_bar.setVisible(False)
        self.audio_progress_label.setText("")

        if timeline_type == 'source':
            self.source_audio_controls.clear_progress()
            self.source_audio_controls.set_error(error)
        else:
            self.edit_audio_controls.clear_progress()
            self.edit_audio_controls.set_error(error)

    def _on_audio_progress(self, timeline_type: str, stage: str, percentage: int):
        """Handle audio processing progress updates"""
        # Show progress in main window status bar
        self.audio_progress_label.setText(tr("audio_controls.progress", stage=stage, percentage=percentage))
        self.audio_progress_bar.setValue(percentage)
        self.audio_progress_bar.setVisible(True)

    def on_open_audio_settings(self):
        """Open the audio settings dialog"""
        if self.audio_settings_dialog is None:
            self.audio_settings_dialog = AudioSettingsDialog(self, self)
        self.audio_settings_dialog.show()
        self.audio_settings_dialog.raise_()
        self.audio_settings_dialog.activateWindow()

    def on_change_language(self, language_code: str):
        previous_language = self.current_language
        selected_language = set_language(language_code)
        self.current_language = selected_language

        if selected_language == "zh-CN":
            self.language_zh_cn_action.setChecked(True)
        else:
            self.language_en_us_action.setChecked(True)

        if selected_language == previous_language:
            return

        QMessageBox.information(
            self,
            tr("app.language_restart_title"),
            tr(
                "app.language_restart_message",
                language_name=tr(f"language.{selected_language}"),
            ),
        )

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

        # Serial panel signals
        serial_panel.refresh_requested.connect(self._refresh_serial_ports)
        serial_panel.connect_requested.connect(self.logic.connect_serial)
        serial_panel.disconnect_requested.connect(self.logic.disconnect_serial)
        serial_panel.offset_changed.connect(self._on_serial_offset_changed)
        serial_panel.auth_lic_changed.connect(self._on_serial_auth_lic_changed)
        self._restore_device_output_offsets()

        # Initial port list
        self._refresh_serial_ports()

    def _coerce_offset(self, value, fallback):
        try:
            offset = int(value)
        except (TypeError, ValueError):
            offset = fallback
        return max(-1000, min(1000, offset))

    def _restore_device_output_offsets(self):
        """Restore device output settings from QSettings and sync UI + logic."""
        settings = QSettings("LumaFlow", "LumaFlow")

        serial_fallback = 200
        serial_offset = self._coerce_offset(settings.value("device_output/serial_offset_ms"), serial_fallback)
        serial_auth_lic = settings.value("device_output/serial_auth_lic", "", str)

        serial_panel = self.device_output_widget.serial_panel

        serial_panel.offset_spin.blockSignals(True)
        serial_panel.offset_spin.setValue(serial_offset)
        serial_panel.offset_spin.blockSignals(False)
        serial_panel.auth_lic_edit.blockSignals(True)
        serial_panel.set_auth_lic(serial_auth_lic)
        serial_panel.auth_lic_edit.blockSignals(False)

        serial_panel.set_default_offset(serial_offset)

        self.logic.set_serial_offset(serial_offset)
        self.logic.set_serial_auth_lic(serial_auth_lic)
        self._persist_device_output_settings(serial_offset=serial_offset, serial_auth_lic=serial_auth_lic)
        serial_panel.set_auth_status("Not Sent")
        serial_panel.set_lic_info(self.logic.get_serial_auth_lic_info())

    def _persist_device_output_settings(self, serial_offset=None, serial_auth_lic=None):
        settings = QSettings("LumaFlow", "LumaFlow")
        if serial_offset is None:
            serial_offset = self.logic.serial_device.get_offset()
        if serial_auth_lic is None:
            serial_auth_lic = self.logic.serial_auth_lic
        settings.setValue("device_output/serial_offset_ms", int(serial_offset))
        settings.setValue("device_output/serial_auth_lic", serial_auth_lic)

    @Slot(int)
    def _on_serial_offset_changed(self, offset_ms):
        self.logic.set_serial_offset(offset_ms)
        self._persist_device_output_settings(serial_offset=offset_ms)

    @Slot(str)
    def _on_serial_auth_lic_changed(self, lic_text):
        self.logic.set_serial_auth_lic(lic_text)
        self._persist_device_output_settings(serial_auth_lic=lic_text)

    def on_about(self):
        from .dialogs import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec()

    def _is_source_timeline_shortcut_context(self) -> bool:
        return self.source_timeline.hasFocus() or self.source_audio_track.hasFocus()

    def _get_preview_widget_for_timeline_action(self, default_to_edit: bool = False):
        if self._is_source_timeline_shortcut_context():
            return self.source_preview_widget
        if default_to_edit or self.edit_timeline.hasFocus() or self.edit_audio_track.hasFocus():
            return self.edit_preview_widget
        return None

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
