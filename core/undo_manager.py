import pandas as pd

class UndoManager:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def execute(self, command):
        command.execute()
        self.undo_stack.append(command)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)

    def redo(self):
        if not self.redo_stack:
            return
        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)

class UndoCommand:
    """撤销命令的基类"""
    def __init__(self, manager, description=""):
        self.manager = manager  # DataManager 实例
        self.description = description

    def execute(self):
        raise NotImplementedError

    def undo(self):
        raise NotImplementedError

class PasteCommand(UndoCommand):
    """粘贴操作的命令"""
    def __init__(self, manager, clipboard, at_ms):
        df_to_paste = clipboard.get_clipboard()
        super().__init__(manager, f"粘贴 {len(df_to_paste)} 帧")
        self.at_ms = at_ms
        self.pasted_df = df_to_paste
        self.original_df_segment = None # 用于存储被覆盖的数据

    def execute(self):
        if self.pasted_df.empty:
            raise ValueError("剪贴板为空。")
        # 计算将被覆盖的时间范围
        time_offset = self.pasted_df['frame_time_ms'].iloc[0]
        start_overwrite = self.at_ms
        end_overwrite = self.at_ms + (self.pasted_df['frame_time_ms'].max() - time_offset)
        
        # 保存被覆盖的原始数据，以便撤销
        self.original_df_segment = self.manager.get_segment(start_overwrite, end_overwrite)
        
        # 执行粘贴
        self.manager.paste_df(self.at_ms, self.pasted_df)

    def undo(self):
        # 计算粘贴数据的时间范围
        time_offset = self.pasted_df['frame_time_ms'].iloc[0]
        start_pasted = self.at_ms
        end_pasted = self.at_ms + (self.pasted_df['frame_time_ms'].max() - time_offset)
        
        # 1. 删除刚刚粘贴的数据
        self.manager.delete_segment(start_pasted, end_pasted)
        
        # 2. 恢复之前被覆盖的数据
        if self.original_df_segment is not None and not self.original_df_segment.empty:
            # 使用 paste_df 来恢复，因为它能处理时间戳重叠
            self.manager.paste_df(self.original_df_segment['frame_time_ms'].min(), self.original_df_segment)

class CopyCommand(UndoCommand):
    """复制操作的命令"""
    def __init__(self, manager, clipboard, start_ms, end_ms):
        super().__init__(manager, f"复制 {start_ms:.2f}-{end_ms:.2f} ms 片段")
        self.clipboard = clipboard
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.previous_clipboard = None

    def execute(self):
        # 保存旧的剪贴板内容以便撤销
        self.previous_clipboard = self.clipboard.get_clipboard()
        
        segment = self.manager.get_segment(self.start_ms, self.end_ms)
        if segment.empty:
            raise ValueError("选中区域内没有可复制的数据。")
        
        self.clipboard.set_clipboard(segment)

    def undo(self):
        # 恢复旧的剪贴板
        if self.previous_clipboard is not None:
            self.clipboard.set_clipboard(self.previous_clipboard)

class CutCommand(UndoCommand):
    """剪切操作的命令（复合命令：复制+删除）"""
    def __init__(self, manager, clipboard, start_ms, end_ms):
        super().__init__(manager, f"剪切 {start_ms:.2f}-{end_ms:.2f} ms 片段")
        self.clipboard = clipboard
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.cut_df = None
        self.previous_clipboard = None

    def execute(self):
        self.cut_df = self.manager.get_segment(self.start_ms, self.end_ms)
        if self.cut_df.empty:
            raise ValueError("选中区域内没有可剪切的数据。")
        
        # 保存旧的剪贴板
        self.previous_clipboard = self.clipboard.get_clipboard()
        
        # 复制到剪贴板
        self.clipboard.set_clipboard(self.cut_df)
        
        # 从时间轴删除
        self.manager.delete_segment(self.start_ms, self.end_ms)

    def undo(self):
        if self.cut_df is None:
            return
        
        # 恢复被剪切的数据
        self.manager.paste_df(self.cut_df['frame_time_ms'].min(), self.cut_df)
        # 恢复旧的剪贴板
        if self.previous_clipboard is not None:
            self.clipboard.set_clipboard(self.previous_clipboard)

class OffsetCommand(UndoCommand):
    """数据偏移（移动）操作的命令"""
    def __init__(self, manager, start_ms, end_ms, offset_ms):
        super().__init__(manager, f"片段偏移 {offset_ms:+.2f} ms")
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.offset_ms = offset_ms
        self.moved_df = None
        self.original_first_frame_time = None

    def execute(self):
        # 1. 获取并保存要移动的数据
        self.moved_df = self.manager.get_segment(self.start_ms, self.end_ms)
        if self.moved_df is None or self.moved_df.empty:
            # 如果没有数据，这是一个无效命令，抛出异常
            raise ValueError("选中区域内没有可移动的数据。")
        
        # 2. 保存精确的原始位置
        self.original_first_frame_time = self.moved_df['frame_time_ms'].iloc[0]

        # 3. 从原始位置删除
        self.manager.delete_segment(self.start_ms, self.end_ms)

        # 4. 计算新位置并粘贴
        new_position = self.original_first_frame_time + self.offset_ms
        self.manager.paste_df(new_position, self.moved_df)

    def undo(self):
        if self.moved_df is None:
            return # 如果没有移动过数据，则无法撤销

        # 1. 计算当前数据所在的位置
        current_start_pos = self.original_first_frame_time + self.offset_ms
        duration = self.moved_df['frame_time_ms'].max() - self.moved_df['frame_time_ms'].min()
        current_end_pos = current_start_pos + duration

        # 2. 从当前（新）位置删除
        self.manager.delete_segment(current_start_pos, current_end_pos)

        # 3. 粘贴回原始位置
        self.manager.paste_df(self.original_first_frame_time, self.moved_df)

class DeleteCommand(UndoCommand):
    """删除操作的命令"""
    def __init__(self, manager, start_ms, end_ms):
        super().__init__(manager, f"删除 {start_ms:.2f}-{end_ms:.2f} ms 片段")
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.deleted_df = None

    def execute(self):
        # 保存被删除的数据以便撤销
        self.deleted_df = self.manager.get_segment(self.start_ms, self.end_ms)
        if self.deleted_df is None or self.deleted_df.empty:
            raise ValueError("选中区域内没有可删除的数据。")
        
        # 执行删除
        self.manager.delete_segment(self.start_ms, self.end_ms)

    def undo(self):
        if self.deleted_df is None or self.deleted_df.empty:
            return
            
        # 恢复被删除的数据
        self.manager.paste_df(self.deleted_df['frame_time_ms'].min(), self.deleted_df)

class InsertFrameCommand(UndoCommand):
    """插入单帧的命令"""
    def __init__(self, manager, at_ms, frame_type='blackout', **kwargs):
        super().__init__(manager, f"插入{kwargs.get('marker', frame_type)}帧")
        self.at_ms = at_ms
        self.frame_type = frame_type
        self.kwargs = kwargs
        self.original_df_segment = None
        self.inserted_frame_df = None

    def execute(self):
        # 创建要插入的帧数据
        new_frame = {col: 0 for col in self.manager.main_df.columns if col not in ['frame_time_ms', 'frame_id', 'frame_type', 'marker']}
        new_frame['frame_time_ms'] = self.at_ms
        new_frame['frame_type'] = self.frame_type
        new_frame['marker'] = self.kwargs.get('marker', '')
        
        if self.frame_type == 'color':
            color = self.kwargs.get('color', {'r': 15, 'g': 15, 'b': 15})
            function = self.kwargs.get('function', 0)
            for i in range(10):
                new_frame[f'ch{i}_function'] = function
                new_frame[f'ch{i}_red'] = color['r']
                new_frame[f'ch{i}_green'] = color['g']
                new_frame[f'ch{i}_blue'] = color['b']
        
        self.inserted_frame_df = pd.DataFrame([new_frame])
        
        # 保存可能被覆盖的原始数据
        self.original_df_segment = self.manager.get_segment(self.at_ms, self.at_ms)
        
        # 执行插入
        self.manager.paste_df(self.at_ms, self.inserted_frame_df)

    def undo(self):
        if self.inserted_frame_df is None:
            return
            
        # 删除插入的帧
        self.manager.delete_segment(self.at_ms, self.at_ms)
        
        # 恢复原始数据（如果有的话）
        if self.original_df_segment is not None and not self.original_df_segment.empty:
            self.manager.paste_df(self.original_df_segment['frame_time_ms'].min(), self.original_df_segment)

class InsertEffectCommand(UndoCommand):
    """插入光效的命令"""
    def __init__(self, manager, at_ms, effect_df, effect_name):
        super().__init__(manager, f"插入{effect_name}效果({len(effect_df)}帧)")
        self.at_ms = at_ms
        self.effect_df = effect_df.copy()
        self.effect_name = effect_name
        self.original_df_segment = None

    def execute(self):
        if self.effect_df.empty:
            raise ValueError("光效数据为空。")
            
        # 计算光效覆盖的时间范围
        time_offset = self.effect_df['frame_time_ms'].iloc[0]
        effect_start = self.at_ms
        effect_end = self.at_ms + (self.effect_df['frame_time_ms'].max() - time_offset)
        
        # 保存被覆盖的原始数据
        self.original_df_segment = self.manager.get_segment(effect_start, effect_end)
        
        # 执行插入
        self.manager.paste_df(self.at_ms, self.effect_df)

    def undo(self):
        if self.effect_df.empty:
            return
            
        # 计算要删除的光效范围
        time_offset = self.effect_df['frame_time_ms'].iloc[0]
        effect_start = self.at_ms
        effect_end = self.at_ms + (self.effect_df['frame_time_ms'].max() - time_offset)
        
        # 删除插入的光效
        self.manager.delete_segment(effect_start, effect_end)
        
        # 恢复原始数据
        if self.original_df_segment is not None and not self.original_df_segment.empty:
            self.manager.paste_df(self.original_df_segment['frame_time_ms'].min(), self.original_df_segment)

class AddMarkerCommand(UndoCommand):
    """添加标记的命令"""
    def __init__(self, manager, at_ms, marker_name=None):
        super().__init__(manager, f"添加标记: {marker_name or '未命名标记'}")
        self.at_ms = at_ms
        self.marker_name = marker_name
        self.original_marker = None
        self.frame_index = None

    def execute(self):
        if self.manager.main_df.empty:
            raise ValueError("时间轴为空，无法添加标记。")
            
        # 如果未提供标记名称，提示用户输入
        if not self.marker_name:
            self.marker_name = input("请输入标记名称: ").strip()
            if not self.marker_name:
                raise ValueError("标记名称不能为空。")
        
        # 找到最接近的帧
        closest_index = self.manager.main_df.iloc[(self.manager.main_df['frame_time_ms'] - self.at_ms).abs().argsort()[:1]].index[0]
        self.frame_index = closest_index
        
        # 保存原始标记（如果有的话）
        self.original_marker = self.manager.main_df.loc[closest_index, 'marker']
        
        # 添加新标记
        self.manager.main_df.loc[closest_index, 'marker'] = self.marker_name

    def undo(self):
        if self.frame_index is not None:
            # 恢复原始标记
            self.manager.main_df.loc[self.frame_index, 'marker'] = self.original_marker if self.original_marker else ""

class UpdateMarkerCommand(UndoCommand):
    """更新标记的命令"""
    def __init__(self, manager, at_ms, marker_name):
        super().__init__(manager, f"更新标记: {marker_name}")
        self.at_ms = at_ms
        self.marker_name = marker_name
        self.original_marker = None
        self.frame_index = None

    def execute(self):
        if self.manager.main_df.empty:
            raise ValueError("时间轴为空，无法更新标记。")

        # 找到最接近的帧
        closest_index = self.manager.main_df.iloc[(self.manager.main_df['frame_time_ms'] - self.at_ms).abs().argsort()[:1]].index[0]
        self.frame_index = closest_index

        # 保存原始标记
        self.original_marker = self.manager.main_df.loc[closest_index, 'marker']

        # 更新标记
        self.manager.main_df.loc[closest_index, 'marker'] = self.marker_name

    def undo(self):
        if self.frame_index is not None:
            # 恢复原始标记
            self.manager.main_df.loc[self.frame_index, 'marker'] = self.original_marker if self.original_marker else ""


class UpdateFrameCommand(UndoCommand):
    """
    Per PRD 5.1: Update an existing frame's color and function values.
    Used by the 'E' shortcut to edit frames without delete/recreate.
    """
    def __init__(self, manager, frame_time_ms, color, function, marker=None):
        super().__init__(manager, f"编辑帧 @ {frame_time_ms:.2f}ms")
        self.frame_time_ms = frame_time_ms
        self.new_color = color  # {'r': 0-15, 'g': 0-15, 'b': 0-15}
        self.new_function = function
        self.new_marker = marker
        self.frame_index = None
        self.original_values = None

    def execute(self):
        if self.manager.main_df.empty:
            raise ValueError("时间轴为空，无法编辑帧。")

        # Find the exact frame at this time
        mask = self.manager.main_df['frame_time_ms'] == self.frame_time_ms
        if not mask.any():
            # Find closest frame within tolerance
            diffs = (self.manager.main_df['frame_time_ms'] - self.frame_time_ms).abs()
            closest_idx = diffs.idxmin()
            if diffs[closest_idx] > 250:  # 250ms tolerance
                raise ValueError(f"未找到时间 {self.frame_time_ms}ms 附近的帧。")
            self.frame_index = closest_idx
        else:
            self.frame_index = self.manager.main_df[mask].index[0]

        # Save original values for undo
        row = self.manager.main_df.loc[self.frame_index]
        self.original_values = {
            'marker': row.get('marker', ''),
        }
        for i in range(10):
            self.original_values[f'ch{i}_function'] = row.get(f'ch{i}_function', 0)
            self.original_values[f'ch{i}_red'] = row.get(f'ch{i}_red', 0)
            self.original_values[f'ch{i}_green'] = row.get(f'ch{i}_green', 0)
            self.original_values[f'ch{i}_blue'] = row.get(f'ch{i}_blue', 0)

        # Apply new values to all channels
        for i in range(10):
            self.manager.main_df.loc[self.frame_index, f'ch{i}_function'] = self.new_function
            self.manager.main_df.loc[self.frame_index, f'ch{i}_red'] = self.new_color['r']
            self.manager.main_df.loc[self.frame_index, f'ch{i}_green'] = self.new_color['g']
            self.manager.main_df.loc[self.frame_index, f'ch{i}_blue'] = self.new_color['b']

        if self.new_marker is not None:
            self.manager.main_df.loc[self.frame_index, 'marker'] = self.new_marker

    def undo(self):
        if self.frame_index is None or self.original_values is None:
            return

        # Restore original values
        for key, value in self.original_values.items():
            self.manager.main_df.loc[self.frame_index, key] = value
