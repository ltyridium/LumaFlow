"""
Timeline Tool Pattern - Per PRD Section 3
Decouples interaction logic from TimelineWidget using a Tool State Machine.
"""
from abc import ABC, abstractmethod
from enum import Enum, auto
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent


class ToolType(Enum):
    SELECTION = auto()
    HAND = auto()


class TimelineTool(ABC):
    """Abstract base class for timeline interaction tools."""

    def __init__(self, timeline_widget):
        self.timeline = timeline_widget
        self.is_active = False

    @abstractmethod
    def on_mouse_press(self, event: QMouseEvent, pos: QPointF) -> bool:
        """Handle mouse press. Return True if event was handled."""
        pass

    @abstractmethod
    def on_mouse_move(self, event: QMouseEvent, pos: QPointF) -> bool:
        """Handle mouse move. Return True if event was handled."""
        pass

    @abstractmethod
    def on_mouse_release(self, event: QMouseEvent, pos: QPointF) -> bool:
        """Handle mouse release. Return True if event was handled."""
        pass

    def on_wheel(self, event: QWheelEvent, pos: QPointF) -> bool:
        """Handle wheel event. Default implementation for all tools."""
        modifiers = event.modifiers()
        delta = event.angleDelta().y()

        if modifiers == Qt.NoModifier:
            # 滚轮上下滚动: 水平缩放时间轴（放大/缩小时间显示）
            # Per user table: "滚轮上下滚动" -> "水平缩放时间轴"
            factor = 0.9 if delta > 0 else 1.1
            self.timeline.zoom_at_position(pos.x(), factor)
            return True
        elif modifiers == Qt.ShiftModifier:
            # Shift + 滚轮: 水平滚动时间轴视图
            # Per user table: "Shift + 滚轮" -> "水平滚动时间轴视图"
            self.timeline.scroll_horizontal(delta)
            return True
        elif modifiers == Qt.AltModifier:
            # Alt + Wheel: Vertical Zoom (Audio) - Forwarded to TimelineWidget
            self.timeline.vertical_zoom(delta)
            return True
        elif modifiers == Qt.ControlModifier:
            # Ctrl + Wheel: Standard Zoom (as fallback or alternative)
            factor = 0.9 if delta > 0 else 1.1
            self.timeline.zoom_at_position(pos.x(), factor)
            return True

        return False

    def on_key_press(self, event: QKeyEvent) -> bool:
        """Handle key press. Return True if event was handled."""
        return False

    def activate(self):
        """Called when this tool becomes active."""
        self.is_active = True

    def deactivate(self):
        """Called when this tool is deactivated."""
        self.is_active = False


class SelectionTool(TimelineTool):
    """
    Default selection tool per PRD 3.1.
    - Left Click: Select frame / Move Playhead (Snap enabled)
    - Left Drag (on item): Move selected frames / Adjust Region edges
    - Left Drag (empty): Box Select / Clear Selection
    - Right Click: Context Menu + Auto-snap to nearest frame
    """

    def __init__(self, timeline_widget):
        super().__init__(timeline_widget)
        self.drag_mode = None  # 'playhead', 'region_start', 'region_end', 'offset', None
        self.drag_start_pos = None
        self.snap_enabled = True  # Per PRD 3.2: Snapping enabled by default

    def on_mouse_press(self, event: QMouseEvent, pos: QPointF) -> bool:
        time_ms = pos.x()
        button = event.button()
        modifiers = event.modifiers()

        if button == Qt.LeftButton:
            shift_held = bool(modifiers & Qt.ShiftModifier)
            ctrl_held = bool(modifiers & Qt.ControlModifier)

            if shift_held:
                # Shift + Click: 扩展选区（参考 Audition）
                start, end = self.timeline.region_item.getRegion()
                if abs(end - start) > 1:  # 有选区
                    mid = (start + end) / 2
                    if time_ms < mid:
                        # 光标更靠近起点，扩展起点
                        self.timeline.region_item.setRegion([time_ms, end])
                    else:
                        # 光标更靠近终点，扩展终点
                        self.timeline.region_item.setRegion([start, time_ms])
                else:
                    # 无选区，从播放头位置开始扩展
                    playhead = self.timeline.get_playback_head_time()
                    self.timeline.region_item.setRegion([min(playhead, time_ms), max(playhead, time_ms)])
                return True
            elif ctrl_held:
                # Ctrl + Click: Start offset drag if in selection
                if self.timeline.is_in_selected_region(time_ms):
                    self.drag_mode = 'offset'
                    self.drag_start_pos = time_ms
                    self.timeline.start_offset_drag(time_ms)
                    return True

            # Check if clicking on region edges for resize
            edge = self.timeline.get_region_edge_at(time_ms)
            if edge:
                self.drag_mode = edge  # 'region_start' or 'region_end'
                return True

            # Default: 定位播放头，并准备拖动选区
            self.drag_mode = 'region_select'
            self.drag_start_pos = time_ms
            if not self.timeline.is_playing():
                snapped = self.timeline.snap_to_nearest_frame(time_ms)
                self.timeline.set_playback_head_time(snapped)
            return True

        elif button == Qt.RightButton:
            # Per PRD 5.3: Right Click - Show context menu (不定位播放头)
            self.timeline.show_context_menu(event.globalPosition().toPoint(), time_ms)
            return True

        return False

    def on_mouse_move(self, event: QMouseEvent, pos: QPointF) -> bool:
        time_ms = pos.x()
        modifiers = event.modifiers()

        # Per PRD 3.2: Shift toggles snapping during drag
        snap = not bool(modifiers & Qt.ShiftModifier)

        if self.drag_mode == 'region_select':
            # 拖动创建选区
            if self.drag_start_pos is not None:
                start = min(self.drag_start_pos, time_ms)
                end = max(self.drag_start_pos, time_ms)
                self.timeline.region_item.setRegion([start, end])
            return True
        elif self.drag_mode == 'region_end':
            if snap:
                time_ms = self.timeline.snap_to_nearest_frame(time_ms)
            self.timeline.update_region_selection(time_ms)
            return True
        elif self.drag_mode == 'region_start':
            if snap:
                time_ms = self.timeline.snap_to_nearest_frame(time_ms)
            self.timeline.resize_region_start(time_ms)
            return True
        elif self.drag_mode == 'offset':
            offset = time_ms - self.drag_start_pos
            self.timeline.update_offset_drag(offset)
            return True

        # Update cursor based on hover position
        edge = self.timeline.get_region_edge_at(time_ms)
        if edge:
            self.timeline.setCursor(Qt.SizeHorCursor)
        else:
            self.timeline.setCursor(Qt.ArrowCursor)

        return False

    def on_mouse_release(self, event: QMouseEvent, pos: QPointF) -> bool:
        if self.drag_mode == 'offset':
            self.timeline.finish_offset_drag()
        elif self.drag_mode in ('region_start', 'region_end'):
            self.timeline.finish_region_selection()

        self.drag_mode = None
        self.drag_start_pos = None
        self.snap_enabled = True  # Reset to default
        return True


class HandTool(TimelineTool):
    """
    Hand/Pan tool per PRD 3.1.
    - Left Drag: Pan View
    - Middle Drag: Pan View (same behavior)
    """

    def __init__(self, timeline_widget):
        super().__init__(timeline_widget)
        self.is_panning = False
        self.pan_start_screen_x = None  # 使用屏幕坐标避免抖动

    def on_mouse_press(self, event: QMouseEvent, pos: QPointF) -> bool:
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.is_panning = True
            self.pan_start_screen_x = event.position().x()
            self.timeline.setCursor(Qt.ClosedHandCursor)
            return True
        return False

    def on_mouse_move(self, event: QMouseEvent, pos: QPointF) -> bool:
        if self.is_panning and self.pan_start_screen_x is not None:
            # 使用屏幕坐标计算像素偏移，再转换为视图坐标
            screen_delta = event.position().x() - self.pan_start_screen_x
            view_range = self.timeline.plot_item.viewRange()[0]
            view_width = view_range[1] - view_range[0]
            plot_width = self.timeline.plot_item.width()
            delta_x = screen_delta * view_width / plot_width if plot_width > 0 else 0
            self.timeline.pan_view(delta_x)
            self.pan_start_screen_x = event.position().x()
            return True
        return False

    def on_mouse_release(self, event: QMouseEvent, pos: QPointF) -> bool:
        if self.is_panning:
            self.is_panning = False
            self.pan_start_screen_x = None
            self.timeline.setCursor(Qt.OpenHandCursor)
            return True
        return False

    def activate(self):
        super().activate()
        self.timeline.setCursor(Qt.OpenHandCursor)

    def deactivate(self):
        super().deactivate()
        self.timeline.setCursor(Qt.ArrowCursor)


class ToolManager:
    """
    Manages tool switching and temporary tool activation.
    Per PRD 3.1: Middle Drag activates temporary pan regardless of current tool.
    """

    def __init__(self, timeline_widget):
        self.timeline = timeline_widget
        self.tools = {
            ToolType.SELECTION: SelectionTool(timeline_widget),
            ToolType.HAND: HandTool(timeline_widget),
        }
        self.current_tool_type = ToolType.SELECTION
        self.temp_tool_type = None  # For temporary tool activation (e.g., middle mouse pan)
        self.tools[self.current_tool_type].activate()

    @property
    def active_tool(self) -> TimelineTool:
        """Get the currently active tool (temp or permanent)."""
        if self.temp_tool_type:
            return self.tools[self.temp_tool_type]
        return self.tools[self.current_tool_type]

    def set_tool(self, tool_type: ToolType):
        """Switch to a different tool."""
        if tool_type != self.current_tool_type:
            self.tools[self.current_tool_type].deactivate()
            self.current_tool_type = tool_type
            self.tools[self.current_tool_type].activate()

    def on_mouse_press(self, event: QMouseEvent, pos: QPointF) -> bool:
        # Middle mouse always activates temporary hand tool
        if event.button() == Qt.MiddleButton:
            self.temp_tool_type = ToolType.HAND
            self.tools[ToolType.HAND].activate()
            return self.tools[ToolType.HAND].on_mouse_press(event, pos)

        return self.active_tool.on_mouse_press(event, pos)

    def on_mouse_move(self, event: QMouseEvent, pos: QPointF) -> bool:
        return self.active_tool.on_mouse_move(event, pos)

    def on_mouse_release(self, event: QMouseEvent, pos: QPointF) -> bool:
        result = self.active_tool.on_mouse_release(event, pos)

        # Deactivate temporary tool on release
        if self.temp_tool_type and event.button() == Qt.MiddleButton:
            self.tools[self.temp_tool_type].deactivate()
            self.temp_tool_type = None

        return result

    def on_wheel(self, event: QWheelEvent, pos: QPointF) -> bool:
        return self.active_tool.on_wheel(event, pos)

    def on_key_press(self, event: QKeyEvent) -> bool:
        return self.active_tool.on_key_press(event)
