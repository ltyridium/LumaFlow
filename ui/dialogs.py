from PySide6.QtWidgets import (
    QDialog, QGridLayout, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit,
    QColorDialog, QDialogButtonBox, QGroupBox, QComboBox, QTextBrowser,
    QWidget, QSlider, QListWidget, QListWidgetItem
)
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, Signal
import math
import numpy as np
import platform
import vlc
from core.metadata import APP_METADATA

class EffectDialog(QDialog):
    """A general-purpose dialog for configuring lighting effects."""
    def __init__(self, title, params_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.params = {}

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        for config in params_config:
            label = QLabel(config['label'])
            widget = None
            if config['type'] == 'float':
                widget = QDoubleSpinBox()
                widget.setRange(config.get('min', 0.0), config.get('max', 100000.0))
                widget.setValue(config.get('default', 1000.0))
                widget.setDecimals(2)
                widget.setSingleStep(100) # Make scrolling more useful
            elif config['type'] == 'int':
                widget = QSpinBox()
                widget.setRange(config.get('min', 1), config.get('max', 1000))
                widget.setValue(config.get('default', 10))
            elif config['type'] == 'color':
                widget = QPushButton("选择颜色...")
                widget.color = QColor(config.get('default', '#FFFFFF'))
                widget.setStyleSheet(f"background-color: {widget.color.name()}; color: {'black' if widget.color.lightness() > 127 else 'white'};")
                widget.clicked.connect(lambda _, w=widget: self.select_color(w))

            if widget:
                form_layout.addRow(label, widget)
                self.params[config['name']] = widget

        main_layout.addLayout(form_layout)

        # Use QDialogButtonBox for standard OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("生成")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.setMinimumWidth(350) # Set a minimum width but allow expansion

    def select_color(self, button):
        # Create HSV color picker dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("选择颜色")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        # HSV Color Wheel
        color_wheel = HSVColorWheelWidget(dialog)
        layout.addWidget(color_wheel)

        # Brightness slider
        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("亮度:"))
        brightness_slider = QSlider(Qt.Orientation.Horizontal)
        brightness_slider.setRange(0, 100)
        brightness_slider.setValue(100)
        brightness_layout.addWidget(brightness_slider)
        layout.addLayout(brightness_layout)

        # Preview and RGB values
        preview_layout = QHBoxLayout()
        color_preview = QLabel("预览")
        color_preview.setMinimumSize(80, 60)
        color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_preview.setAutoFillBackground(True)
        preview_layout.addWidget(color_preview)

        rgb_layout = QFormLayout()
        r_spin = QSpinBox(); r_spin.setRange(0, 15); r_spin.setValue(7)
        g_spin = QSpinBox(); g_spin.setRange(0, 15); g_spin.setValue(7)
        b_spin = QSpinBox(); b_spin.setRange(0, 15); b_spin.setValue(7)
        rgb_layout.addRow("R:", r_spin)
        rgb_layout.addRow("G:", g_spin)
        rgb_layout.addRow("B:", b_spin)
        preview_layout.addLayout(rgb_layout)
        layout.addLayout(preview_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Connect signals
        def update_preview():
            from core.color_calibration import color_calibration
            r, g, b = r_spin.value(), g_spin.value(), b_spin.value()
            r_255 = color_calibration.r_lut[r]
            g_255 = color_calibration.g_lut[g]
            b_255 = color_calibration.b_lut[b]
            lightness = (0.299 * r_255 + 0.587 * g_255 + 0.114 * b_255)
            text_color = "black" if lightness > 128 else "white"
            color_preview.setStyleSheet(f"background-color: rgb({r_255}, {g_255}, {b_255}); color: {text_color}; border: 1px solid gray;")
            button.color = QColor(r_255, g_255, b_255)

        color_wheel.color_selected.connect(lambda r, g, b: (r_spin.setValue(r), g_spin.setValue(g), b_spin.setValue(b)))
        brightness_slider.valueChanged.connect(lambda v: color_wheel.set_value(v / 100.0))
        r_spin.valueChanged.connect(update_preview)
        g_spin.valueChanged.connect(update_preview)
        b_spin.valueChanged.connect(update_preview)

        update_preview()

        if dialog.exec():
            from core.color_calibration import color_calibration
            r, g, b = r_spin.value(), g_spin.value(), b_spin.value()
            r_255 = color_calibration.r_lut[r]
            g_255 = color_calibration.g_lut[g]
            b_255 = color_calibration.b_lut[b]
            button.color = QColor(r_255, g_255, b_255)
            text_color = 'black' if button.color.lightness() > 127 else 'white'
            button.setStyleSheet(f"background-color: {button.color.name()}; color: {text_color};")

    def get_params(self):
        results = {}
        for name, widget in self.params.items():
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                results[name] = widget.value()
            elif isinstance(widget, QPushButton):
                r, g, b, _ = widget.color.getRgb()
                results[name] = {'r': round(r / 17), 'g': round(g / 17), 'b': round(b / 17)}
        return results

class CalibrationDialog(QDialog):
    """Dialog for adjusting RGB display calibration."""
    def __init__(self, current_gains, parent=None):
        super().__init__(parent)
        self.setWindowTitle("显示色彩校准")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        info_lbl = QLabel("调整显示层的RGB增益以匹配硬件表现。\n此操作不修改原始数据 (0-15)。")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        form_layout = QFormLayout()

        # Red
        self.r_spin = QDoubleSpinBox()
        self.r_spin.setRange(0.1, 3.0)
        self.r_spin.setSingleStep(0.1)
        self.r_spin.setValue(current_gains['r'])
        form_layout.addRow("红色增益 (Red):", self.r_spin)

        # Green
        self.g_spin = QDoubleSpinBox()
        self.g_spin.setRange(0.1, 3.0)
        self.g_spin.setSingleStep(0.1)
        self.g_spin.setValue(current_gains['g'])
        form_layout.addRow("绿色增益 (Green):", self.g_spin)

        # Blue
        self.b_spin = QDoubleSpinBox()
        self.b_spin.setRange(0.1, 3.0)
        self.b_spin.setSingleStep(0.1)
        self.b_spin.setValue(current_gains['b'])
        form_layout.addRow("蓝色增益 (Blue):", self.b_spin)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_defaults)
        layout.addWidget(button_box)

    def reset_defaults(self):
        self.r_spin.setValue(1.0)
        self.g_spin.setValue(1.0)
        self.b_spin.setValue(1.0)

    def get_values(self):
        return self.r_spin.value(), self.g_spin.value(), self.b_spin.value()
class ColorPickerDialog(QDialog):
    """A dialog for inserting a custom color keyframe."""
    def __init__(self, parent=None, prefill_color=None, prefill_function=0, prefill_marker=""):
        super().__init__(parent)
        self.setWindowTitle("自定义颜色帧")
        self.setModal(True)
        self._prefill_color = prefill_color or {'r': 15, 'g': 15, 'b': 15}
        self._prefill_function = prefill_function
        self._prefill_marker = prefill_marker
        self.init_ui()
        self.update_preview()
        self.setMinimumWidth(400)

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Color Selection Group ---
        color_group = QGroupBox("颜色选择")
        color_group_layout = QHBoxLayout(color_group)

        # HSV Color Wheel
        wheel_layout = QVBoxLayout()
        self.color_wheel = HSVColorWheelWidget(self)
        wheel_layout.addWidget(self.color_wheel)

        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("亮度:"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(100)
        brightness_layout.addWidget(self.brightness_slider)
        wheel_layout.addLayout(brightness_layout)
        color_group_layout.addLayout(wheel_layout)

        # RGB Numeric Input
        numeric_layout = QVBoxLayout()
        form_layout = QFormLayout()
        self.r_spinbox = QSpinBox(); self.r_spinbox.setRange(0, 15); self.r_spinbox.setValue(self._prefill_color['r'])
        self.g_spinbox = QSpinBox(); self.g_spinbox.setRange(0, 15); self.g_spinbox.setValue(self._prefill_color['g'])
        self.b_spinbox = QSpinBox(); self.b_spinbox.setRange(0, 15); self.b_spinbox.setValue(self._prefill_color['b'])
        form_layout.addRow("红 (R):", self.r_spinbox)
        form_layout.addRow("绿 (G):", self.g_spinbox)
        form_layout.addRow("蓝 (B):", self.b_spinbox)
        numeric_layout.addLayout(form_layout)

        self.color_preview = QLabel("预览")
        self.color_preview.setMinimumSize(80, 60)
        self.color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_preview.setAutoFillBackground(True)
        numeric_layout.addWidget(self.color_preview)
        color_group_layout.addLayout(numeric_layout)

        main_layout.addWidget(color_group)

        # --- Additional Options Group ---
        options_group = QGroupBox("选项")
        options_layout = QFormLayout(options_group)
        
        self.function_combo = QComboBox()
        self.function_combo.addItems(["0 - 常亮", "1 - 1Hz频闪", "2 - 2Hz频闪", "3 - 4Hz频闪"])
        self.function_combo.setCurrentIndex(self._prefill_function)
        options_layout.addRow("灯光功能:", self.function_combo)

        self.marker_edit = QLineEdit()
        self.marker_edit.setPlaceholderText("可选，留空则使用默认")
        self.marker_edit.setText(self._prefill_marker)
        options_layout.addRow("标记名称:", self.marker_edit)
        main_layout.addWidget(options_group)

        # --- Presets Group ---
        preset_group = QGroupBox("快速预设")
        preset_layout = QGridLayout(preset_group)
        presets = [
            ("黑", (0, 0, 0)), ("粉白", (15, 15, 15)), ("红", (15, 0, 0)), ("绿", (0, 15, 0)),
            ("蓝", (0, 0, 15)), ("黄", (15, 15, 0)), ("紫", (15, 0, 15)), ("青", (0, 15, 15))
        ]
        for i, (name, (r, g, b)) in enumerate(presets):
            btn = QPushButton(name)
            # [REMOVED] btn.setMaximumSize(40, 30) - Let buttons size themselves.
            btn.clicked.connect(lambda checked, r=r, g=g, b=b: self.set_preset_color(r, g, b))
            preset_layout.addWidget(btn, i // 4, i % 4) # Arrange in a 2x4 grid
        main_layout.addWidget(preset_group)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # --- Connections ---
        self.color_wheel.color_selected.connect(self.on_wheel_color_selected)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        self.r_spinbox.valueChanged.connect(self.on_spinbox_changed)
        self.g_spinbox.valueChanged.connect(self.on_spinbox_changed)
        self.b_spinbox.valueChanged.connect(self.on_spinbox_changed)

    def set_preset_color(self, r, g, b):
        self.r_spinbox.setValue(r)
        self.g_spinbox.setValue(g)
        self.b_spinbox.setValue(b)

    def on_wheel_color_selected(self, r, g, b):
        """Update spinboxes when color wheel is clicked"""
        self.r_spinbox.blockSignals(True)
        self.g_spinbox.blockSignals(True)
        self.b_spinbox.blockSignals(True)
        self.r_spinbox.setValue(r)
        self.g_spinbox.setValue(g)
        self.b_spinbox.setValue(b)
        self.r_spinbox.blockSignals(False)
        self.g_spinbox.blockSignals(False)
        self.b_spinbox.blockSignals(False)
        self.update_preview()

    def on_brightness_changed(self, value):
        """Update color wheel brightness"""
        self.color_wheel.set_value(value / 100.0)

    def on_spinbox_changed(self):
        """Update preview when spinboxes change"""
        self.update_preview()

    def update_preview(self):
        r, g, b = self.r_spinbox.value(), self.g_spinbox.value(), self.b_spinbox.value()
        from core.color_calibration import color_calibration
        r_255 = color_calibration.r_lut[r]
        g_255 = color_calibration.g_lut[g]
        b_255 = color_calibration.b_lut[b]

        lightness = (0.299 * r_255 + 0.587 * g_255 + 0.114 * b_255)
        text_color = "black" if lightness > 128 else "white"

        self.color_preview.setStyleSheet(
            f"background-color: rgb({r_255}, {g_255}, {b_255});"
            f"color: {text_color};"
            "border: 1px solid gray;"
        )

    def get_values(self):
        """Returns the selected values from the dialog."""
        return {
            'color': {
                'r': self.r_spinbox.value(),
                'g': self.g_spinbox.value(),
                'b': self.b_spinbox.value()
            },
            'function': self.function_combo.currentIndex(),
            'marker': self.marker_edit.text().strip()
        }

class GradientPreviewWidget(QWidget):
    """Interactive gradient preview with draggable control points"""
    control_point_added = Signal(float)
    control_point_moved = Signal(int, float)
    control_point_selected = Signal(int)
    control_point_edit_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.control_points = []
        self.gradient_pixmap = None
        self.selected_point = -1
        self.dragging_point = -1
        self.hover_point = -1
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_gradient_data(self, control_points, gradient_pixmap):
        self.control_points = control_points
        self.gradient_pixmap = gradient_pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.gradient_pixmap:
            scaled = self.gradient_pixmap.scaled(self.width(), 100, Qt.AspectRatioMode.IgnoreAspectRatio)
            painter.drawPixmap(0, 0, scaled)

        for i, point in enumerate(self.control_points):
            x = int(point['position'] * (self.width() - 1))
            is_start_end = i == 0 or i == len(self.control_points) - 1

            from core.color_calibration import color_calibration
            from utils.numba_funcs import hsv_to_rgb_4bit
            h, s, v = point['hue'], point['saturation'], point['value']
            r_4bit, g_4bit, b_4bit = hsv_to_rgb_4bit(h, s, v)
            r_8bit = color_calibration.r_lut[r_4bit]
            g_8bit = color_calibration.g_lut[g_4bit]
            b_8bit = color_calibration.b_lut[b_4bit]

            if is_start_end:
                painter.setBrush(QBrush(QColor(r_8bit, g_8bit, b_8bit)))
                if i == self.selected_point or i == self.hover_point:
                    painter.setPen(QPen(Qt.GlobalColor.white, 3))
                else:
                    painter.setPen(QPen(Qt.GlobalColor.black, 2))
                painter.drawRect(x - 6, 102, 12, 12)
            else:
                path = QPainterPath()
                path.moveTo(x, 100)
                path.lineTo(x - 6, 112)
                path.lineTo(x + 6, 112)
                path.closeSubpath()
                painter.setBrush(QBrush(QColor(r_8bit, g_8bit, b_8bit)))
                if i == self.selected_point or i == self.hover_point:
                    painter.setPen(QPen(Qt.GlobalColor.white, 3))
                else:
                    painter.setPen(QPen(Qt.GlobalColor.black, 2))
                painter.drawPath(path)

    def mousePressEvent(self, event):
        clicked_point = self._get_point_at_pos(event.pos())
        if clicked_point >= 0:
            self.selected_point = clicked_point
            self.dragging_point = clicked_point
            self.control_point_selected.emit(clicked_point)
        else:
            if len(self.control_points) < 5:
                pos = event.pos().x() / self.width()
                pos = max(0.01, min(0.99, pos))
                self.control_point_added.emit(pos)
        self.update()

    def mouseDoubleClickEvent(self, event):
        clicked_point = self._get_point_at_pos(event.pos())
        if clicked_point >= 0:
            self.control_point_edit_requested.emit(clicked_point)

    def mouseMoveEvent(self, event):
        if self.dragging_point >= 0:
            is_start_end = self.dragging_point == 0 or self.dragging_point == len(self.control_points) - 1
            if not is_start_end:
                new_pos = event.pos().x() / self.width()
                new_pos = max(0.01, min(0.99, new_pos))
                self.control_point_moved.emit(self.dragging_point, new_pos)
        else:
            old_hover = self.hover_point
            self.hover_point = self._get_point_at_pos(event.pos())

            # Update cursor based on hover state
            if self.hover_point >= 0:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif event.pos().y() >= 0 and event.pos().y() <= 115 and len(self.control_points) < 5:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

            if old_hover != self.hover_point:
                self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_point = -1

    def _get_point_at_pos(self, pos):
        for i, point in enumerate(self.control_points):
            x = int(point['position'] * self.width())
            if abs(pos.x() - x) < 10 and pos.y() >= 100 and pos.y() <= 115:
                return i
        return -1

class HSVColorWheelWidget(QWidget):
    """HSV color wheel widget showing LUT-calibrated 4-bit colors"""
    color_selected = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wheel_radius = 100
        self.selected_hue = 0.0
        self.selected_saturation = 1.0
        self.selected_value = 1.0
        self.wheel_pixmap = None
        self.setMinimumSize(220, 250)
        self._render_wheel()

    def _render_wheel(self):
        """Pre-render HSV color wheel with LUT-calibrated colors"""
        from core.color_calibration import color_calibration
        from utils.numba_funcs import hsv_to_rgb_4bit
        size = self.wheel_radius * 2 + 20
        self.wheel_pixmap = QPixmap(size, size)
        self.wheel_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(self.wheel_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = center_y = size // 2

        for y in range(size):
            for x in range(size):
                dx = x - center_x
                dy = y - center_y
                dist = math.sqrt(dx * dx + dy * dy)

                if dist <= self.wheel_radius:
                    angle = math.atan2(dy, dx)
                    hue = (angle + math.pi) / (2 * math.pi)
                    saturation = min(dist / self.wheel_radius, 1.0)

                    r_4bit, g_4bit, b_4bit = hsv_to_rgb_4bit(hue, saturation, self.selected_value)

                    r_8bit = color_calibration.r_lut[r_4bit]
                    g_8bit = color_calibration.g_lut[g_4bit]
                    b_8bit = color_calibration.b_lut[b_4bit]

                    painter.setPen(QColor(r_8bit, g_8bit, b_8bit))
                    painter.drawPoint(x, y)

        painter.end()

    def paintEvent(self, event):
        if not self.wheel_pixmap:
            return

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.wheel_pixmap)

        center_x = center_y = (self.wheel_radius * 2 + 20) // 2
        sel_x = center_x + int(self.selected_saturation * self.wheel_radius * math.cos(self.selected_hue * 2 * math.pi - math.pi))
        sel_y = center_y + int(self.selected_saturation * self.wheel_radius * math.sin(self.selected_hue * 2 * math.pi - math.pi))

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(sel_x - 5, sel_y - 5, 10, 10)
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.drawEllipse(sel_x - 4, sel_y - 4, 8, 8)

    def mousePressEvent(self, event):
        center_x = center_y = (self.wheel_radius * 2 + 20) // 2
        dx = event.pos().x() - center_x
        dy = event.pos().y() - center_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= self.wheel_radius:
            angle = math.atan2(dy, dx)
            self.selected_hue = (angle + math.pi) / (2 * math.pi)
            self.selected_saturation = min(dist / self.wheel_radius, 1.0)
            self.update()
            self._emit_color()

    def set_value(self, value):
        """Set brightness value (0-1)"""
        self.selected_value = value
        self._render_wheel()
        self.update()
        self._emit_color()

    def _emit_color(self):
        """Convert HSV to 4-bit RGB and emit signal"""
        from utils.numba_funcs import hsv_to_rgb_4bit
        r_4bit, g_4bit, b_4bit = hsv_to_rgb_4bit(self.selected_hue, self.selected_saturation, self.selected_value)
        self.color_selected.emit(r_4bit, g_4bit, b_4bit)

class GradientDialog(QDialog):
    """Dialog for creating HSV gradient effects with timeline preview"""
    def __init__(self, parent=None, start_ms=0, end_ms=5000, data_manager=None):
        super().__init__(parent)
        self.setWindowTitle("生成渐变效果")
        self.setModal(True)
        self.setMinimumSize(600, 400)

        self.start_ms = start_ms
        self.end_ms = end_ms
        self.data_manager = data_manager

        start_color = self._get_nearest_frame_color(start_ms)
        end_color = self._get_nearest_frame_color(end_ms)

        self.control_points = [
            {'position': 0.0, 'hue': start_color['h'], 'saturation': start_color['s'], 'value': start_color['v']},
            {'position': 1.0, 'hue': end_color['h'], 'saturation': end_color['s'], 'value': end_color['v']}
        ]
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Interactive preview
        preview_group = QGroupBox("预览 (点击添加控制点，拖动调整位置，双击编辑颜色)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_widget = GradientPreviewWidget()
        self.preview_widget.control_point_added.connect(self.on_point_added)
        self.preview_widget.control_point_moved.connect(self.on_point_moved)
        self.preview_widget.control_point_edit_requested.connect(self.on_point_edit_requested)
        preview_layout.addWidget(self.preview_widget)
        main_layout.addWidget(preview_group)

        # Options
        options_layout = QFormLayout()

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["RGB混合", "HSV顺时针", "HSV逆时针"])
        self.direction_combo.currentIndexChanged.connect(self.update_preview)
        options_layout.addRow("混合模式:", self.direction_combo)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(10.0, 1000.0)
        self.interval_spin.setValue(100.0)
        self.interval_spin.setSingleStep(10.0)
        options_layout.addRow("帧间隔 (ms):", self.interval_spin)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(100.0, 60000.0)
        self.duration_spin.setValue(self.end_ms - self.start_ms)
        self.duration_spin.setSingleStep(100.0)
        options_layout.addRow("持续时间 (ms):", self.duration_spin)

        main_layout.addLayout(options_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.update_preview()

    def on_point_added(self, position):
        """Handle control point added from preview widget"""
        if len(self.control_points) >= 5:
            return

        self.control_points.append({
            'position': position,
            'hue': 0.33,
            'saturation': 1.0,
            'value': 1.0
        })
        self.control_points.sort(key=lambda p: p['position'])
        self.update_preview()

    def on_point_moved(self, index, new_position):
        """Handle control point moved from preview widget"""
        if index > 0 and index < len(self.control_points) - 1:
            self.control_points[index]['position'] = new_position
            self.control_points.sort(key=lambda p: p['position'])
            self.update_preview()

    def on_point_edit_requested(self, index):
        """Handle double-click on control point to edit color"""
        if index < 0 or index >= len(self.control_points):
            return

        point = self.control_points[index]
        r, g, b = self._hsv_to_rgb(point['hue'], point['saturation'], point['value'])

        dialog = ColorPickerDialog(self, prefill_color={'r': r, 'g': g, 'b': b})
        if dialog.exec():
            values = dialog.get_values()
            color = values['color']
            h, s, v = self._rgb_to_hsv(color['r'], color['g'], color['b'])
            self.control_points[index]['hue'] = h
            self.control_points[index]['saturation'] = s
            self.control_points[index]['value'] = v
            self.update_preview()

    def update_preview(self):
        from core.color_calibration import color_calibration
        from utils.numba_funcs import compute_gradient_colors

        times = np.arange(0, 1000, 10)
        positions = np.array([p['position'] for p in self.control_points])
        hues = np.array([p['hue'] for p in self.control_points])
        saturations = np.array([p['saturation'] for p in self.control_points])
        values = np.array([p['value'] for p in self.control_points])

        mode = self.direction_combo.currentIndex()  # 0=RGB, 1=HSV CW, 2=HSV CCW

        colors = compute_gradient_colors(times, positions, hues, saturations, values, 10, mode)

        width = len(times)
        height = 10
        pixmap = QPixmap(width, height * 10)
        painter = QPainter(pixmap)

        for t in range(width):
            for ch in range(height):
                r_4bit = int(colors[t, ch, 0])
                g_4bit = int(colors[t, ch, 1])
                b_4bit = int(colors[t, ch, 2])

                r_8bit = color_calibration.r_lut[r_4bit]
                g_8bit = color_calibration.g_lut[g_4bit]
                b_8bit = color_calibration.b_lut[b_4bit]

                painter.setPen(QColor(r_8bit, g_8bit, b_8bit))
                painter.drawLine(t, ch * 10, t, (ch + 1) * 10)

        painter.end()
        self.preview_widget.set_gradient_data(self.control_points, pixmap)

    def _get_nearest_frame_color(self, time_ms):
        """Get color from nearest frame at given time"""
        if not self.data_manager or self.data_manager.main_df.empty:
            return {'h': 0.0, 's': 1.0, 'v': 1.0}

        df = self.data_manager.main_df
        time_diffs = (df['frame_time_ms'] - time_ms).abs()
        nearest_idx = time_diffs.idxmin()
        nearest_frame = df.loc[nearest_idx]

        r = nearest_frame['ch0_red']
        g = nearest_frame['ch0_green']
        b = nearest_frame['ch0_blue']

        h, s, v = self._rgb_to_hsv(r, g, b)
        return {'h': h, 's': s, 'v': v}

    def _rgb_to_hsv(self, r, g, b):
        """Convert 4-bit RGB (0-15) to HSV (0-1)"""
        from utils.numba_funcs import rgb_4bit_to_hsv
        return rgb_4bit_to_hsv(r, g, b)

    def _hsv_to_rgb(self, h, s, v):
        """Convert HSV (0-1) to 4-bit RGB (0-15)"""
        from utils.numba_funcs import hsv_to_rgb_4bit
        return hsv_to_rgb_4bit(h, s, v)

    def get_params(self):
        return {
            'control_points': self.control_points,
            'mode': self.direction_combo.currentIndex(),  # 0=RGB, 1=HSV CW, 2=HSV CCW
            'interval': self.interval_spin.value(),
            'duration': self.duration_spin.value()
        }

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 LumaFlow")
        self.setFixedSize(450, 380)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 头部：图标和基本信息
        header_layout = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap("resources/icons/icon.png").scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        
        info_v_layout = QVBoxLayout()
        title_label = QLabel("LumaFlow")
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        version_label = QLabel(f"版本: {APP_METADATA['version']}")
        info_v_layout.addWidget(title_label)
        info_v_layout.addWidget(version_label)
        
        header_layout.addWidget(logo_label)
        header_layout.addLayout(info_v_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 中间：详细描述和链接
        content = QTextBrowser()
        content.setOpenExternalLinks(True)
        # 使用 HTML 渲染，增加系统环境检测，方便排错
        vlc_ver = vlc.libvlc_get_version().decode() if hasattr(vlc, 'libvlc_get_version') else "未找到"
        
        html = f"""
        <p>{APP_METADATA['description']}</p>
        <hr>
        <b>开发者:</b> {APP_METADATA['author']} <br>
        <b>GitHub:</b> <a href="{APP_METADATA['github']}">代码仓库</a> | 
        <b>Bilibili:</b> <a href="{APP_METADATA['bilibili']}">关注作者</a>
        <hr>
        <p style='color: gray; font-size: 9pt;'>
        <b>运行环境:</b><br>
        Python: {platform.python_version()}<br>
        VLC Core: {vlc_ver}<br>
        OS: {platform.system()} {platform.release()}
        </p>
        <p align="center" style="font-style: italic;">关注洛天依谢谢喵 <a href="{APP_METADATA['luotianyi']}">qwq)</a></p>
        """
        content.setHtml(html)
        layout.addWidget(content)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("确定")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)