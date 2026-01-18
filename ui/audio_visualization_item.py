"""
音频频谱可视化组件 - 瓦片化渲染模式
使用后台线程预渲染瓦片，UI 线程只负责贴图。
"""
import time
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Signal, Slot
from PySide6.QtGui import QImage, QPainter, QColor, QBrush
import numpy as np
from typing import Optional, Set

from utils.tile_cache import TileCache


class AudioVisualizationItem(pg.GraphicsObject):
    """基于瓦片的音频频谱可视化组件"""

    # 动态瓦片时长：Level 0 为 5s, Level 1 为 80s, Level 2 为 1280s
    LEVEL_TILE_DURATIONS = [5000, 80000, 1280000]

    # 信号：请求渲染瓦片
    # (audio_data, cache_key, start_ms, end_ms, colormap, request_time)
    request_tile = Signal(object, str, float, float, str, float)

    def __init__(self, y_position: float = 0.0, height: float = 128.0):
        super().__init__()
        self.audio_data = None
        self.y_position = y_position
        self.height = height  # 默认 128 对应 128 个 Mel 频段
        self.colormap_name = 'inferno'  # 默认使用 inferno 颜色映射

        self._tile_cache: Optional[TileCache] = None
        self._pending_tiles: Set[str] = set()
        self._bounding_rect = QRectF()

        # 占位符颜色（深灰色）
        self._placeholder_brush = QBrush(QColor(60, 60, 60, 200))

    def set_tile_cache(self, cache: TileCache):
        """设置瓦片缓存（由外部注入）"""
        self._tile_cache = cache

    def setAudioData(self, audio_data):
        """设置音频数据"""
        self.audio_data = audio_data
        self._pending_tiles.clear()
        self._update_bounding_rect()
        self.update()

    def setHeight(self, height: float):
        """设置可视化高度"""
        self.height = height
        self._update_bounding_rect()
        self.update()

    def setYPosition(self, y_position: float):
        """设置 Y 位置"""
        self.y_position = y_position
        self._update_bounding_rect()
        self.update()

    def setColormap(self, colormap_name: str):
        """设置颜色映射"""
        self.colormap_name = colormap_name
        self._pending_tiles.clear()
        self.update()

    def _update_bounding_rect(self):
        """更新边界矩形"""
        if self.audio_data is None:
            self._bounding_rect = QRectF()
        else:
            # 使用实际的 Mel 频段数量作为高度
            n_mels = self.audio_data.spectrogram.shape[0] if self.audio_data.spectrogram is not None else self.N_MELS
            self.height = n_mels
            self._bounding_rect = QRectF(
                0,
                self.y_position,
                self.audio_data.duration_ms,
                self.height
            )

    def boundingRect(self):
        """返回边界矩形"""
        return self._bounding_rect

    def _get_level_for_zoom(self, ms_per_pixel: float) -> int:
        """根据缩放级别选择合适的分辨率"""
        if ms_per_pixel < 50:
            return 0  # 极度放大
        elif ms_per_pixel < 800:
            return 1  # 中等范围
        else:
            return 2  # 长视频全局视图

    def _make_cache_key(self, tile_id: int, level: int) -> str:
        """生成缓存键"""
        if self.audio_data is None:
            return ""
        return f"{self.audio_data.video_path}_{self.audio_data.channel_mode}_{self.colormap_name}_{tile_id}_{level}"

    def _get_visible_tile_ids(self, x_min: float, x_max: float, level: int) -> list:
        """计算可见瓦片 ID 列表"""
        if self.audio_data is None:
            return []

        duration_ms = self.LEVEL_TILE_DURATIONS[level]
        start_tile = max(0, int(x_min // duration_ms))
        end_tile = min(
            int(self.audio_data.duration_ms // duration_ms) + 1,
            int(x_max // duration_ms) + 1
        )

        return list(range(start_tile, end_tile))

    def paint(self, painter, option, widget):
        """渲染 - 纯贴图模式"""
        if self.audio_data is None or self._tile_cache is None:
            return

        view_box = self.getViewBox()
        if view_box is None:
            return

        view_range = view_box.viewRange()
        x_range = view_range[0]

        # 限制到数据范围
        x_min = max(0, x_range[0])
        x_max = min(self.audio_data.duration_ms, x_range[1])

        if x_max <= x_min:
            return

        # 计算缩放级别
        view_width_pixels = view_box.width()
        if view_width_pixels <= 0:
            return
        ms_per_pixel = (x_max - x_min) / view_width_pixels
        level = self._get_level_for_zoom(ms_per_pixel)
        tile_dur = self.LEVEL_TILE_DURATIONS[level]

        # 获取可见瓦片
        tile_ids = self._get_visible_tile_ids(x_min, x_max, level)

        painter.save()
        try:
            # PySide6 中 QPainter.SmoothTransformation 已被移至 QPainter.RenderHint
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            for tile_id in tile_ids:
                cache_key = self._make_cache_key(tile_id, level)
                if not cache_key:
                    continue

                # 计算瓦片时间范围
                tile_start = tile_id * tile_dur
                tile_end = min(
                    (tile_id + 1) * tile_dur,
                    self.audio_data.duration_ms
                )

                # 瓦片绘制区域
                tile_rect = QRectF(
                    tile_start,
                    self.y_position,
                    tile_end - tile_start,
                    self.height
                )

                # 尝试从缓存获取
                cached_image = self._tile_cache.get(cache_key)

                if cached_image is not None:
                    # 缓存命中：绘制瓦片
                    painter.drawImage(tile_rect, cached_image)
                else:
                    # 缓存未命中：绘制占位符
                    painter.fillRect(tile_rect, self._placeholder_brush)

                    # 发射渲染请求（如果尚未请求）
                    if cache_key not in self._pending_tiles:
                        self._pending_tiles.add(cache_key)
                        self.request_tile.emit(
                            self.audio_data,
                            cache_key,
                            tile_start,
                            tile_end,
                            self.colormap_name,
                            time.time()
                        )
        finally:
            painter.restore()

    @Slot(str, object)
    def on_tile_ready(self, cache_key: str, image: QImage):
        """瓦片渲染完成回调"""
        if self._tile_cache is None:
            return

        # 存入缓存
        self._tile_cache.put(cache_key, image)

        # 从待处理集合移除
        self._pending_tiles.discard(cache_key)

        # 触发重绘
        self.update()
