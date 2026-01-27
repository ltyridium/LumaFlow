from PySide6.QtWidgets import (
    QDialog, QGridLayout, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit,
    QColorDialog, QDialogButtonBox, QGroupBox, QComboBox, QTextBrowser
)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Qt
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
        color = QColorDialog.getColor(button.color, self)
        if color.isValid():
            button.color = color
            # Set text color based on background brightness for readability
            text_color = 'black' if color.lightness() > 127 else 'white'
            button.setStyleSheet(f"background-color: {color.name()}; color: {text_color};")

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
        color_group = QGroupBox("RGB颜色值 (0-15)")
        color_group_layout = QHBoxLayout(color_group)

        form_layout = QFormLayout()
        self.r_spinbox = QSpinBox(); self.r_spinbox.setRange(0, 15); self.r_spinbox.setValue(self._prefill_color['r'])
        self.g_spinbox = QSpinBox(); self.g_spinbox.setRange(0, 15); self.g_spinbox.setValue(self._prefill_color['g'])
        self.b_spinbox = QSpinBox(); self.b_spinbox.setRange(0, 15); self.b_spinbox.setValue(self._prefill_color['b'])
        form_layout.addRow("红 (R):", self.r_spinbox)
        form_layout.addRow("绿 (G):", self.g_spinbox)
        form_layout.addRow("蓝 (B):", self.b_spinbox)
        
        self.color_preview = QLabel("预览")
        self.color_preview.setMinimumSize(80, 60)
        self.color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_preview.setAutoFillBackground(True)

        color_group_layout.addLayout(form_layout)
        color_group_layout.addWidget(self.color_preview)
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
        self.r_spinbox.valueChanged.connect(self.update_preview)
        self.g_spinbox.valueChanged.connect(self.update_preview)
        self.b_spinbox.valueChanged.connect(self.update_preview)

    def set_preset_color(self, r, g, b):
        self.r_spinbox.setValue(r)
        self.g_spinbox.setValue(g)
        self.b_spinbox.setValue(b)

    def update_preview(self):
        r, g, b = self.r_spinbox.value(), self.g_spinbox.value(), self.b_spinbox.value()
        r_255, g_255, b_255 = int(r * 17), int(g * 17), int(b * 17)
        
        # Set text color based on background for readability
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