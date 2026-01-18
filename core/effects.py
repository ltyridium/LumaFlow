import numpy as np
import pandas as pd
from utils.numba_funcs import compute_breathing_brightness, compute_rainbow_colors

class EffectGenerator:
    @staticmethod
    def create_breathing_df(duration_ms, interval_ms, color, min_bright, max_bright, columns):
        """使用Numba优化的呼吸效果生成"""
        times = np.arange(0, duration_ms, interval_ms)
        
        if len(times) == 0:
            return pd.DataFrame()
        
        brightness_values = compute_breathing_brightness(times, min_bright, max_bright)
        
        n_frames = len(times)
        data = {}
        
        for col in columns:
            if col not in ['frame_time_ms', 'frame_id', 'frame_type', 'marker']:
                data[col] = np.zeros(n_frames, dtype=np.int32)
        
        data['frame_time_ms'] = times
        data['frame_id'] = np.arange(1, n_frames + 1)
        data['frame_type'] = ['breathing'] * n_frames
        data['marker'] = [''] * n_frames
        
        for i in range(10):
            data[f'ch{i}_function'] = np.zeros(n_frames, dtype=np.int32)
            data[f'ch{i}_red'] = np.round(color['r'] * brightness_values).astype(np.int32)
            data[f'ch{i}_green'] = np.round(color['g'] * brightness_values).astype(np.int32)
            data[f'ch{i}_blue'] = np.round(color['b'] * brightness_values).astype(np.int32)
        
        return pd.DataFrame(data)

    @staticmethod
    def create_rainbow_df(duration_ms, interval_ms, speed, columns):
        """使用Numba优化的彩虹流光效果生成"""
        times = np.arange(0, duration_ms, interval_ms)
        
        if len(times) == 0:
            return pd.DataFrame()
        
        colors_array = compute_rainbow_colors(times, speed, 10)
        
        n_frames = len(times)
        data = {}
        
        for col in columns:
            if col not in ['frame_time_ms', 'frame_id', 'frame_type', 'marker']:
                data[col] = np.zeros(n_frames, dtype=np.int32)
        
        data['frame_time_ms'] = times
        data['frame_id'] = np.arange(1, n_frames + 1)
        data['frame_type'] = ['rainbow'] * n_frames
        data['marker'] = [''] * n_frames
        
        for i in range(10):
            data[f'ch{i}_function'] = np.zeros(n_frames, dtype=np.int32)
            data[f'ch{i}_red'] = colors_array[:, i, 0].astype(np.int32)
            data[f'ch{i}_green'] = colors_array[:, i, 1].astype(np.int32)
            data[f'ch{i}_blue'] = colors_array[:, i, 2].astype(np.int32)
        
        return pd.DataFrame(data)
