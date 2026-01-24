import pandas as pd
import numpy as np
from utils.performance import perf_monitor

class DataManager:
    def __init__(self):
        self.main_df = pd.DataFrame()
        self._default_frame_interval_ms = 166.67
    
    def load_csv(self, file_path: str) -> bool:
        try:
            self.main_df = pd.read_csv(file_path)
            if 'frame_time_ms' not in self.main_df.columns: self.main_df = pd.DataFrame(); return False
            if 'marker' not in self.main_df.columns: self.main_df['marker'] = ""
            self.main_df['marker'] = self.main_df['marker'].fillna("")
            return True
        except Exception as e: print(f"Error loading CSV: {e}"); self.main_df = pd.DataFrame(); return False
    
    def get_full_data(self) -> pd.DataFrame: return self.main_df.copy()
    
    def get_segment(self, start_ms: float, end_ms: float) -> pd.DataFrame:
        if self.main_df.empty: return pd.DataFrame()
        return self.main_df[(self.main_df['frame_time_ms'] >= start_ms) & (self.main_df['frame_time_ms'] <= end_ms)].copy()

    
    def add_marker(self, at_ms: float, name: str):
        if self.main_df.empty: return
        closest_index = self.main_df.iloc[(self.main_df['frame_time_ms'] - at_ms).abs().argsort()[:1]].index[0]
        self.main_df.loc[closest_index, 'marker'] = name
        
    def update_marker(self, at_ms: float, name: str):
        """更新指定时间的标记"""
        if self.main_df.empty: return
        closest_index = self.main_df.iloc[(self.main_df['frame_time_ms'] - at_ms).abs().argsort()[:1]].index[0]
        self.main_df.loc[closest_index, 'marker'] = name
        
    def get_marker_times(self) -> list:
        if self.main_df.empty: return []
        markers = self.main_df[self.main_df['marker'] != ""]
        return sorted(markers['frame_time_ms'].tolist())
    
    def paste_df(self, at_ms: float, df_to_paste: pd.DataFrame):
        """
        使用优化的异步数据粘贴操作，提供进度反馈。
        """
        if df_to_paste.empty:
            return False
        
        # 对于小数据集，直接使用同步方法
        if len(df_to_paste) < 50:
            return self._paste_df_sync(at_ms, df_to_paste)
        
        # 对于大数据集，使用异步优化方法
        return self._paste_df_async(at_ms, df_to_paste)
    
    def _paste_df_sync(self, at_ms: float, df_to_paste: pd.DataFrame):
        """同步版本，用于小数据集"""
        if df_to_paste.empty:
            return False
        
        perf_monitor.start_timing(f"数据粘贴操作({len(df_to_paste)}帧)")
        
        insert_df = df_to_paste.copy().sort_values('frame_time_ms').reset_index(drop=True)
        
        if not insert_df.empty:
            time_offset = insert_df['frame_time_ms'].iloc[0]
            insert_df['frame_time_ms'] = at_ms + (insert_df['frame_time_ms'] - time_offset)
        
        start_overwrite_ms = insert_df['frame_time_ms'].min()
        end_overwrite_ms = insert_df['frame_time_ms'].max()
        
        mask = (self.main_df['frame_time_ms'] >= start_overwrite_ms) & (self.main_df['frame_time_ms'] <= end_overwrite_ms)
        self.main_df = self.main_df[~mask]
        self.main_df = pd.concat([self.main_df, insert_df], ignore_index=True)
        self.main_df = self.main_df.sort_values('frame_time_ms').reset_index(drop=True)
        self._reassign_frame_ids()
        
        perf_monitor.end_timing(f"数据粘贴操作({len(df_to_paste)}帧)", f"- 主数据集{len(self.main_df)}帧")
        return True
    
    def _paste_df_async(self, at_ms: float, df_to_paste: pd.DataFrame):
        """真正的异步版本，用于大数据集"""
        perf_monitor.start_timing(f"异步数据粘贴操作({len(df_to_paste)}帧)")
        
        try:
            # 使用优化的向量化操作替代DataProcessWorker
            insert_df = df_to_paste.copy()
            
            # 1. 使用NumPy进行时间偏移计算（更快）
            times = insert_df['frame_time_ms'].values
            time_offset = times[0] if len(times) > 0 else 0
            insert_df['frame_time_ms'] = at_ms + (times - time_offset)
            
            # 2. 使用向量化操作确定覆盖范围
            start_overwrite_ms = insert_df['frame_time_ms'].min()
            end_overwrite_ms = insert_df['frame_time_ms'].max()
            
            # 3. 使用布尔索引（比iloc快）删除覆盖范围内的数据
            mask = (self.main_df['frame_time_ms'] >= start_overwrite_ms) & (self.main_df['frame_time_ms'] <= end_overwrite_ms)
            self.main_df = self.main_df[~mask]
            
            # 4. 批量合并操作
            self.main_df = pd.concat([self.main_df, insert_df], ignore_index=True)
            
            # 5. 高效排序（使用sort_values的优化算法）
            self.main_df = self.main_df.sort_values('frame_time_ms', kind='mergesort').reset_index(drop=True)
            self._reassign_frame_ids()
            
            perf_monitor.end_timing(f"异步数据粘贴操作({len(df_to_paste)}帧)", f"- 主数据集{len(self.main_df)}帧")
            return True
            
        except Exception as e:
            perf_monitor.end_timing(f"异步数据粘贴操作({len(df_to_paste)}帧)", f"- 异常: {str(e)}")
            print(f"异步粘贴失败，回退到同步模式: {e}")
            return self._paste_df_sync(at_ms, df_to_paste)

    # --- MODIFIED: `delete_segment` no longer shifts data ---
    def delete_segment(self, start_ms: float, end_ms: float):
        """
        删除指定时间段的所有帧。
        - 不移动任何其他帧，从而在时间轴上留下一个空白区域。
        """
        if self.main_df.empty:
            return False
        
        # 计算被删除的帧数用于性能监控
        delete_mask = (self.main_df['frame_time_ms'] >= start_ms) & (self.main_df['frame_time_ms'] <= end_ms)
        deleted_count = delete_mask.sum()
        
        perf_monitor.start_timing(f"数据删除操作({deleted_count}帧)")
        
        # 只删除指定时间段的帧，不进行任何后续移位
        self.main_df = self.main_df[~delete_mask]
        
        # 重新分配frame_id
        self.main_df = self.main_df.reset_index(drop=True)
        self._reassign_frame_ids()
        
        perf_monitor.end_timing(f"数据删除操作({deleted_count}帧)", f"- 主数据集剩余{len(self.main_df)}帧")
        return True

    
    # --- MODIFIED: `insert_custom_frame` call to paste_df is updated ---
    def insert_custom_frame(self, at_ms: float, frame_type='blackout', **kwargs):
        """
        插入自定义关键帧。
        """
        # 创建一个只包含一行的 DataFrame
        new_frame = {col: 0 for col in self.main_df.columns if col not in ['frame_time_ms', 'frame_id', 'frame_type', 'marker']}
        new_frame['frame_time_ms'] = at_ms
        new_frame['frame_type'] = frame_type
        new_frame['marker'] = kwargs.get('marker', '')
        
        if frame_type == 'color':
            color = kwargs.get('color', {'r': 15, 'g': 15, 'b': 15})
            function = kwargs.get('function', 0)
            for i in range(10):
                new_frame[f'ch{i}_function'] = function
                new_frame[f'ch{i}_red'] = color['r']
                new_frame[f'ch{i}_green'] = color['g']
                new_frame[f'ch{i}_blue'] = color['b']
        
        new_frame_df = pd.DataFrame([new_frame])
        # 调用新的 paste_df，它将自动处理覆盖逻辑
        return self.paste_df(at_ms, new_frame_df)
    
    def _detect_frame_interval(self) -> float:
        if len(self.main_df) < 2:
            return self._default_frame_interval_ms
        intervals = self.main_df['frame_time_ms'].diff().dropna()
        if intervals.empty:
            return self._default_frame_interval_ms
        return intervals.mode().iloc[0] if not intervals.mode().empty else self._default_frame_interval_ms
    
    def _reassign_frame_ids(self):
        if not self.main_df.empty:
            self.main_df['frame_id'] = range(1, len(self.main_df) + 1)
    
    def save_csv(self, file_path: str) -> bool:
        if self.main_df.empty:
            return False
        try:
            save_df = self.main_df.copy()
            self._reassign_frame_ids()
            if 'frame_type' not in save_df.columns: save_df['frame_type'] = 'Type_001'
            if 'marker' not in save_df.columns: save_df['marker'] = ""
            save_df['marker'] = save_df['marker'].fillna("")
            save_df = save_df.sort_values('frame_time_ms').reset_index(drop=True)
            save_df['frame_id'] = range(1, len(save_df) + 1)
            save_df.to_csv(file_path, index=False)
            return True
        except Exception as e:
            print(f"Error saving CSV: {e}")
            return False
    
    def validate_timeline_integrity(self) -> tuple[bool, str]:
        # ... (此方法无需修改)
        if self.main_df.empty: return False, "时间轴为空"
        errors = []
        required_columns = ['frame_time_ms', 'frame_id']
        for col in required_columns:
            if col not in self.main_df.columns: errors.append(f"缺少必需列: {col}")
        if 'frame_time_ms' in self.main_df.columns:
            if self.main_df['frame_time_ms'].duplicated().any(): errors.append("存在重复的时间戳")
        for i in range(10):
            for color in ['red', 'green', 'blue']:
                col_name = f'ch{i}_{color}'
                if col_name in self.main_df.columns:
                    values = self.main_df[col_name]
                    if (values < 0).any() or (values > 15).any(): errors.append(f"{col_name} 值超出范围 (0-15)")
            func_col = f'ch{i}_function'
            if func_col in self.main_df.columns:
                values = self.main_df[func_col]
                if (values < 0).any() or (values > 3).any(): errors.append(f"{func_col} 值超出范围 (0-3)")
        if errors: return False, "; ".join(errors)
        return True, "数据完整性验证通过"

    def get_timeline_stats(self) -> dict:
        # ... (此方法无需修改)
        if self.main_df.empty: return {'total_frames': 0, 'total_duration_ms': 0, 'total_duration_sec': 0, 'marker_count': 0, 'frame_interval_ms': 0, 'start_time_ms': 0, 'end_time_ms': 0}
        total_frames = len(self.main_df)
        start_time = self.main_df['frame_time_ms'].min()
        end_time = self.main_df['frame_time_ms'].max()
        total_duration_ms = end_time - start_time
        marker_count = len(self.main_df[self.main_df['marker'] != ""])
        frame_interval = self._detect_frame_interval()
        return {'total_frames': total_frames, 'total_duration_ms': total_duration_ms, 'total_duration_sec': total_duration_ms / 1000.0, 'marker_count': marker_count, 'frame_interval_ms': frame_interval, 'start_time_ms': start_time, 'end_time_ms': end_time}

    def get_frame_at_ms(self, current_ms: float):
        """
        Gets the data frame corresponding to the last timestamp at or before current_ms.
        Uses binary search for O(log n) lookup.
        """
        if self.main_df.empty:
            return None

        timestamps = self.main_df['frame_time_ms'].values
        idx = np.searchsorted(timestamps, current_ms, side='right') - 1

        if idx >= 0:
            return self.main_df.iloc[idx]
        return None

    def get_frame_index_at_ms(self, current_ms: float):
        """Gets the frame index at the specified time."""
        if self.main_df.empty:
            return None

        timestamps = self.main_df['frame_time_ms'].values
        idx = np.searchsorted(timestamps, current_ms, side='right') - 1

        if idx >= 0:
            return idx
        return None
