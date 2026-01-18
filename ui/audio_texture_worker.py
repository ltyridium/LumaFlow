"""
后台纹理渲染 Worker
负责将音频频谱数据转换为 QImage 瓦片。
"""
import time
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage
import matplotlib.cm as cm



class AudioTextureWorker(QObject):
    texture_ready = Signal(str, object)
    # 增加下采样倍率，适配长视频
    LEVELS_DOWNSAMPLE = [1, 16, 128]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cmap_cache = {}

    @Slot(object, str, float, float, str, float)
    def render_tile(self, audio_data, cache_key: str, start_ms: float, end_ms: float,
                    colormap: str, request_time: float):
        if time.time() - request_time > 5.0: return 

        try:
            # 解析 Level
            level = int(cache_key.split('_')[-1])
            ds_factor = self.LEVELS_DOWNSAMPLE[level] if level < len(self.LEVELS_DOWNSAMPLE) else 1

            # 提取数据
            spec = audio_data.spectrogram
            times = audio_data.times_ms
            
            s_idx = np.searchsorted(times, start_ms, side='left')
            e_idx = np.searchsorted(times, end_ms, side='right')
            
            if e_idx <= s_idx: return
            
            # 切片并下采样
            tile_data = spec[:, s_idx:e_idx:ds_factor]
            if tile_data.size == 0: return


            norm_data = np.clip((tile_data + 80) / 80, 0, 1)

            # 应用 Colormap
            rgb_data = self._apply_colormap(norm_data, colormap)
            rgb_data = np.ascontiguousarray(rgb_data)

            height, width = rgb_data.shape[:2]
            img = QImage(rgb_data.data, width, height, width * 3, QImage.Format_RGB888)
            self.texture_ready.emit(cache_key, img.copy())
            
        except Exception as e:
            print(f"[Worker Error] {e}")

    def _apply_colormap(self, normalized_data: np.ndarray, colormap: str) -> np.ndarray:
        """应用颜色映射"""
        # if not MATPLOTLIB_AVAILABLE:
        #     # 回退：灰度
        #     gray = (normalized_data * 255).astype(np.uint8)
        #     return np.stack([gray, gray, gray], axis=-1)

        # 使用缓存的 colormap 对象
        if colormap not in self._cmap_cache:
            try:
                self._cmap_cache[colormap] = cm.get_cmap(colormap)
            except:
                self._cmap_cache[colormap] = cm.get_cmap('viridis')

        cmap = self._cmap_cache[colormap]
        rgba = cmap(normalized_data)
        rgb = (rgba[:, :, :3] * 255).astype(np.uint8)

        return rgb
