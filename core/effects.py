import numpy as np
import pandas as pd
from utils.numba_funcs import compute_breathing_brightness, compute_rainbow_colors, compute_gradient_colors

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
    def create_intermediate_fill_df(anchor_df, interval_ms, columns):
        """Generate discrete forward-hold intermediate frames between anchors."""
        if anchor_df.empty or interval_ms <= 0:
            return pd.DataFrame(columns=list(columns))

        anchor_df = (
            anchor_df.copy()
            .sort_values('frame_time_ms', kind='mergesort')
            .drop_duplicates(subset=['frame_time_ms'], keep='first')
            .reset_index(drop=True)
        )

        if len(anchor_df) < 2:
            return anchor_df.loc[:, list(columns)].copy()

        generated_rows = []
        interval_ms = float(interval_ms)
        epsilon = 1e-9

        for index in range(len(anchor_df)):
            current_row = anchor_df.iloc[index].copy()
            generated_rows.append(current_row.to_dict())

            if index == len(anchor_df) - 1:
                continue

            next_time = float(anchor_df.iloc[index + 1]['frame_time_ms'])
            insert_time = float(current_row['frame_time_ms']) + interval_ms

            while insert_time < next_time - epsilon:
                new_row = current_row.copy()
                new_row['frame_time_ms'] = float(insert_time)
                if 'frame_id' in new_row:
                    new_row['frame_id'] = 0
                if 'frame_type' in new_row:
                    new_row['frame_type'] = 'intermediate_fill'
                if 'marker' in new_row:
                    new_row['marker'] = ''
                generated_rows.append(new_row.to_dict())
                insert_time += interval_ms

        result_df = pd.DataFrame(generated_rows)

        for column in columns:
            if column not in result_df.columns:
                if column == 'marker':
                    result_df[column] = ''
                elif column == 'frame_type':
                    result_df[column] = 'intermediate_fill'
                else:
                    result_df[column] = 0

        return (
            result_df.loc[:, list(columns)]
            .sort_values('frame_time_ms', kind='mergesort')
            .drop_duplicates(subset=['frame_time_ms'], keep='first')
            .reset_index(drop=True)
        )

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

    @staticmethod
    def create_gradient_df(duration_ms, interval_ms, control_points, mode, columns):
        """生成渐变效果 (mode: 0=RGB混合, 1=HSV顺时针, 2=HSV逆时针)"""
        times = np.arange(0, duration_ms, interval_ms)

        if len(times) == 0:
            return pd.DataFrame()

        positions = np.array([p['position'] for p in control_points])
        hues = np.array([p['hue'] for p in control_points])
        saturations = np.array([p['saturation'] for p in control_points])
        values = np.array([p['value'] for p in control_points])

        colors_array = compute_gradient_colors(times, positions, hues, saturations, values, 10, mode)

        n_frames = len(times)
        data = {}

        for col in columns:
            if col not in ['frame_time_ms', 'frame_id', 'frame_type', 'marker']:
                data[col] = np.zeros(n_frames, dtype=np.int32)

        data['frame_time_ms'] = times
        data['frame_id'] = np.arange(1, n_frames + 1)
        data['frame_type'] = ['gradient'] * n_frames
        data['marker'] = [''] * n_frames

        for i in range(10):
            data[f'ch{i}_function'] = np.zeros(n_frames, dtype=np.int32)
            data[f'ch{i}_red'] = colors_array[:, i, 0].astype(np.int32)
            data[f'ch{i}_green'] = colors_array[:, i, 1].astype(np.int32)
            data[f'ch{i}_blue'] = colors_array[:, i, 2].astype(np.int32)

        return pd.DataFrame(data)
