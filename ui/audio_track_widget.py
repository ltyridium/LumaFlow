"""
独立的音频轨道组件，与主时间轴同步显示音频频谱。
使用瓦片化渲染，支持后台异步加载。
支持 Audition 风格的 Y 轴（频率）交互。
"""
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt
from typing import Optional
import numpy as np

from .audio_visualization_item import AudioVisualizationItem


class TimeAxisItem(pg.AxisItem):
    """时间轴格式化"""
    def tickStrings(self, values, scale, spacing):
        return [f"{int(v // 3600000):02d}:{int((v / 60000) % 60):02d}:{int((v / 1000) % 60):02d}.{int(v % 1000):03d}" for v in values]


class FrequencyAxisItem(pg.AxisItem):
    """频率轴 - 显示 Hz"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mel_frequencies = None

    def tickStrings(self, values, scale, spacing):
        if self.mel_frequencies is None or len(self.mel_frequencies) == 0:
            return [str(int(v)) for v in values]

        result = []
        for v in values:
            idx = int(np.clip(v, 0, len(self.mel_frequencies) - 1))
            hz = self.mel_frequencies[idx]
            if hz >= 1000:
                result.append(f"{hz/1000:.1f}k")
            else:
                result.append(f"{int(hz)}")
        return result


class AudioTrackWidget(pg.PlotWidget):
    """
    独立的音频轨道组件，支持与主时间轴同步。
    使用瓦片化渲染实现流畅的音频频谱显示。
    支持 Y 轴（频率）缩放和拖拽。
    """
    x_range_changed = Signal(float, float)

    def __init__(self, parent=None, audio_manager=None):
        # 创建自定义坐标轴
        self.freq_axis = FrequencyAxisItem(orientation='left')
        self.time_axis = TimeAxisItem(orientation='bottom')
        super().__init__(parent=parent, axisItems={'bottom': self.time_axis, 'left': self.freq_axis})

        self._syncing = False
        self._colormap = 'inferno'  # 默认使用 inferno 颜色映射
        self._audio_manager = None

        # 基本设置
        self.plot_item = self.getPlotItem()
        self.plot_item.hideButtons()
        self.setBackground('#1a1a1a')  # 深色背景更适合频谱图
        self.plot_item.showGrid(x=True, y=False, alpha=0.2)

        # 只启用 X 轴交互，禁用 Y 轴鼠标拖动
        self.setMouseEnabled(x=True, y=False)
        self.plot_item.vb.disableAutoRange(axis=pg.ViewBox.XAxis)
        self.plot_item.vb.disableAutoRange(axis=pg.ViewBox.YAxis)

        # 禁用右键菜单
        self.plot_item.vb.setMenuEnabled(False)

        # 默认 Y 轴不翻转 (Inverted Y = False)
        # 这样 Y=0 在底部，Y=128 在顶部
        # 配合 AudioTextureWorker 中移除 flipud，低频在下，高频在上
        self.plot_item.invertY(False)

        # Y 轴范围设为 0-128（对应 128 个 Mel 频段）
        self.plot_item.setYRange(0, 128, padding=0)
        self.plot_item.setXRange(0, 1000, padding=0)

        # 设置 Y 轴宽度
        self.freq_axis.setWidth(50)

        # 音频可视化项（高度 128 对应 Mel 频段）
        self.audio_viz_item = AudioVisualizationItem(y_position=0, height=128)
        self.plot_item.addItem(self.audio_viz_item)

        # 播放头
        self.playback_head = pg.InfiniteLine(pos=0, angle=90, movable=False, pen=pg.mkPen('r', width=2))
        self.playback_head.setZValue(10)
        self.plot_item.addItem(self.playback_head)

        # 连接视口变化信号
        self.plot_item.vb.sigRangeChanged.connect(self._on_range_changed)

        # 设置 AudioManager（如果提供）
        if audio_manager is not None:
            self.set_audio_manager(audio_manager)

    def set_audio_manager(self, audio_manager):
        """设置 AudioManager 并连接信号"""
        if self._audio_manager is not None:
            # 断开旧连接
            try:
                self.audio_viz_item.request_tile.disconnect()
                self._audio_manager.tile_ready.disconnect(self.audio_viz_item.on_tile_ready)
            except:
                pass

        self._audio_manager = audio_manager

        if audio_manager is not None:
            # 设置瓦片缓存
            self.audio_viz_item.set_tile_cache(audio_manager.tile_cache)

            # 连接信号：可视化项请求瓦片 -> AudioManager 转发到 Worker
            self.audio_viz_item.request_tile.connect(audio_manager.request_tile)

            # 连接信号：Worker 完成瓦片 -> 可视化项更新
            audio_manager.tile_ready.connect(self.audio_viz_item.on_tile_ready)

    def _on_range_changed(self):
        """视口变化时发射信号"""
        if not self._syncing:
            x_range = self.plot_item.viewRange()[0]
            self.x_range_changed.emit(x_range[0], x_range[1])

    def set_x_range(self, x_min: float, x_max: float):
        """设置X轴范围（用于同步）"""
        # If no audio data, use safe default range
        if self.audio_viz_item.audio_data is None:
            x_min, x_max = 0, 1000
        else:
            # Limit range to audio data bounds
            duration = self.audio_viz_item.audio_data.duration_ms
            x_min = max(0, min(x_min, duration))
            x_max = max(0, min(x_max, duration))
            if x_max <= x_min:
                x_min, x_max = 0, duration

        self._syncing = True
        try:
            # 不阻塞信号，确保坐标轴能正确更新
            self.plot_item.setXRange(x_min, x_max, padding=0)
        finally:
            self._syncing = False

    def set_audio_data(self, audio_data):
        """设置音频数据"""
        self.audio_viz_item.setAudioData(audio_data)

        if audio_data is not None:
            # 将频率信息传递给坐标轴
            self.freq_axis.mel_frequencies = audio_data.frequencies

            # 设置 Y 轴范围为实际的 Mel 频段数量
            n_mels = audio_data.spectrogram.shape[0] if audio_data.spectrogram is not None else 128
            self.plot_item.setYRange(0, n_mels, padding=0)

            # 自动调整 X 轴到全长
            self.plot_item.setXRange(0, audio_data.duration_ms, padding=0.02)

    def set_playback_head_time(self, time_ms: float):
        """设置播放头位置"""
        self.playback_head.setValue(time_ms)

    def set_colormap(self, colormap: str):
        """设置颜色映射"""
        self._colormap = colormap
        self.audio_viz_item.setColormap(colormap)

    def reset_y_range(self):
        """重置 Y 轴到完整范围"""
        if self.audio_viz_item.audio_data is not None:
            n_mels = self.audio_viz_item.audio_data.spectrogram.shape[0]
            self.plot_item.setYRange(0, n_mels, padding=0)
        else:
            self.plot_item.setYRange(0, 128, padding=0)

    def zoom_vertical(self, delta: float, center_y: Optional[float] = None):
        """Vertical zoom (Frequency axis)"""
        current_range = self.plot_item.viewRange()[1]
        current_height = current_range[1] - current_range[0]

        zoom_factor = 0.8 if delta > 0 else 1.25
        new_height = current_height * zoom_factor

        # Limit Y axis zoom range
        n_mels = 128
        if self.audio_viz_item.audio_data is not None:
            n_mels = self.audio_viz_item.audio_data.spectrogram.shape[0]

        if new_height < 10:
            new_height = 10
        elif new_height > n_mels:
            new_height = n_mels

        # Calculate new range
        if center_y is None:
            center_y = (current_range[0] + current_range[1]) / 2

        ratio = (center_y - current_range[0]) / current_height if current_height > 0 else 0.5
        new_start = center_y - new_height * ratio
        new_end = new_start + new_height

        # Clamp to valid range
        if new_start < 0:
            new_start = 0
            new_end = new_height
        if new_end > n_mels:
            new_end = n_mels
            new_start = n_mels - new_height

        self.plot_item.setYRange(new_start, new_end, padding=0)

    def wheelEvent(self, event):
        """处理滚轮事件 - Audition 风格交互"""
        delta = event.angleDelta().y()
        modifiers = event.modifiers()

        if modifiers == Qt.ControlModifier:
            # Ctrl+Wheel: X 轴（时间）缩放，以鼠标为中心
            mouse_point = self.plot_item.vb.mapSceneToView(event.scenePosition())
            current_range = self.plot_item.viewRange()[0]
            current_width = current_range[1] - current_range[0]

            zoom_factor = 0.8 if delta > 0 else 1.25
            new_width = current_width * zoom_factor

            # 限制缩放范围
            min_zoom = 100
            max_zoom = 1e8
            if new_width < min_zoom:
                new_width = min_zoom
            elif new_width > max_zoom:
                new_width = max_zoom
            else:
                mouse_x = mouse_point.x()
                ratio = (mouse_x - current_range[0]) / current_width
                new_start = mouse_x - new_width * ratio
                new_end = new_start + new_width
                self.plot_item.setXRange(new_start, new_end, padding=0)
            event.accept()

        elif modifiers == Qt.AltModifier:
            # Alt+Wheel: Y 轴（频率）缩放 - 保留此功能用于频率范围缩放
            # 这是唯一可以改变 Y 轴范围的方式（鼠标拖动已禁用）
            mouse_point = self.plot_item.vb.mapSceneToView(event.scenePosition())
            current_range = self.plot_item.viewRange()[1]
            current_height = current_range[1] - current_range[0]

            zoom_factor = 0.8 if delta > 0 else 1.25
            new_height = current_height * zoom_factor

            # 限制 Y 轴缩放范围
            n_mels = 128
            if self.audio_viz_item.audio_data is not None:
                n_mels = self.audio_viz_item.audio_data.spectrogram.shape[0]

            if new_height < 10:
                new_height = 10
            elif new_height > n_mels:
                new_height = n_mels
            else:
                mouse_y = mouse_point.y()
                ratio = (mouse_y - current_range[0]) / current_height if current_height > 0 else 0.5
                new_start = mouse_y - new_height * ratio
                new_end = new_start + new_height

                # 限制在有效范围内
                if new_start < 0:
                    new_start = 0
                    new_end = new_height
                if new_end > n_mels:
                    new_end = n_mels
                    new_start = n_mels - new_height

                self.plot_item.setYRange(new_start, new_end, padding=0)
            event.accept()

        elif modifiers == Qt.ShiftModifier:
            # Shift+Wheel: 快速水平滚动
            scroll_amount = (delta / 120) * 1000
            current_range = self.plot_item.viewRange()[0]
            self.plot_item.setXRange(current_range[0] - scroll_amount, current_range[1] - scroll_amount, padding=0)
            event.accept()

        elif modifiers == Qt.NoModifier:
            # Wheel: 普通水平滚动
            scroll_amount = (delta / 120) * 100
            current_range = self.plot_item.viewRange()[0]
            self.plot_item.setXRange(current_range[0] - scroll_amount, current_range[1] - scroll_amount, padding=0)
            event.accept()

        else:
            super().wheelEvent(event)
