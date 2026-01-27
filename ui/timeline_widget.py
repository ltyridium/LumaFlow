# Standard library imports
import sys
import os
import time
import threading
import traceback

# Third-party library imports
import pandas as pd
import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn

# PySide6 imports
from PySide6.QtCore import Qt, Signal, QThread, QObject, QRectF, QPointF, Signal as pyqtSignal, QTimer, Slot as pyqtSlot
from PySide6.QtGui import QColor, QPolygonF, QPainterPath, QPainter
from PySide6.QtWidgets import QApplication, QLabel

# Local imports
from core.color_calibration import color_calibration
from utils.performance import perf_monitor
from ui.timeline_tools import ToolManager

class RenderWorker(QObject):
    """
    在背景线程中准备渲染数据的 Worker。
    """
    # --- MODIFIED: 为信号添加一个 bool 标志位 ---
    # 参数：(渲染数据字典, 边界矩形QRectF, 是否为原始数据模式)
    finished = pyqtSignal(dict, QRectF, bool)

    def __init__(self):
        super().__init__()
        self.current_data = pd.DataFrame()
        self.is_running = False

    @pyqtSlot(pd.DataFrame, tuple, float, int)
    def process_data(self, df, view_range, view_width_pixels, num_channels=10):
        """
        接收数据并开始处理的核心槽函数 (V4 - 同时修正颜色保持和颜色延伸)。
        """
        if self.is_running:
            return
        
        self.is_running = True
        
        try:
            x_min, x_max = view_range
            
            if df.empty:
                self.finished.emit({}, QRectF(), False)
                return

            # --- 1. 精确查找渲染所需的数据范围 ---
            times = df['frame_time_ms'].values
            
            # 找到视图左侧的第一个关键帧 (用于颜色保持)
            start_idx = times.searchsorted(x_min, side='right') - 1
            if start_idx < 0:
                start_idx = 0
            
            # 找到视图右侧的第一个关键帧 (用于颜色延伸)
            # 我们需要多找一个点来正确计算最后一个可见块的宽度
            end_idx = times.searchsorted(x_max, side='right') + 1
            # 确保 end_idx 不会超出范围
            if end_idx > len(times):
                end_idx = len(times)

            # --- 2. 高效切片 ---
            df_visible = df.iloc[start_idx:end_idx].copy()

            if df_visible.empty:
                self.finished.emit({}, QRectF(), False)
                return

            # --- 3. 处理左侧的"颜色保持" ---
            first_frame_time = df_visible['frame_time_ms'].iloc[0]
            if first_frame_time < x_min:
                df_visible.iloc[0, df_visible.columns.get_loc('frame_time_ms')] = x_min

            # --- 4. 调用聚合函数 ---
            n_visible = len(df_visible)
            num_bins = min(n_visible, int(view_width_pixels / 6))

            if num_bins > 0:
                # --- MODIFIED: 接收聚合函数返回的两个值 ---
                df_final, is_raw_data = self._aggregate_data(df_visible, num_bins, df)
            else:
                df_final, is_raw_data = pd.DataFrame(), False

            if df_final.empty:
                self.finished.emit({}, QRectF(), is_raw_data)
                return
                
            # =================================================================
            # +++ 新增逻辑：处理右侧的"颜色延伸" +++
            # =================================================================
            # 修正最后一个bin的宽度，让它正确地延伸
            if not df_final.empty:
                # 找到原始数据中，最后一个聚合bin之后的第一个真实关键帧
                last_agg_time = df_final['frame_time_ms'].iloc[-1]
                
                # 在原始完整数据集中找到下一个关键帧的时间
                next_keyframe_index = times.searchsorted(last_agg_time, side='right')
                
                # 如果存在下一个关键帧
                if next_keyframe_index < len(times):
                    next_keyframe_time = times[next_keyframe_index]
                    # 计算正确的宽度：从最后一个bin的开始到下一个关键帧的开始
                    correct_width = next_keyframe_time - last_agg_time
                    df_final.iloc[-1, df_final.columns.get_loc('width')] = correct_width
                else:
                    # 如果不存在下一个关键帧（已经是时间轴末尾）
                    # 则让其宽度延伸到至少覆盖当前视图的右边界
                    current_end_pos = last_agg_time + df_final['width'].iloc[-1]
                    if x_max > current_end_pos:
                        df_final.iloc[-1, df_final.columns.get_loc('width')] = x_max - last_agg_time

            # --- 5. 准备渲染数据 (此部分不变) ---
            n_frames_final = len(df_final)
            n_points = n_frames_final * num_channels
            
            render_data = {
                'x': np.repeat(df_final['frame_time_ms'].values, num_channels),
                'y': np.tile(np.arange(num_channels), n_frames_final),
                'w': np.repeat(df_final['width'].values, num_channels),
                'r': np.zeros(n_points, dtype=np.uint8),
                'g': np.zeros(n_points, dtype=np.uint8),
                'b': np.zeros(n_points, dtype=np.uint8),
            }
            
            for i in range(num_channels):
                indices = np.arange(i, n_points, num_channels)

                # Apply per-channel LUT lookup based on calibration
                raw_r = df_final[f'ch{i}_red'].values.astype(int)
                raw_g = df_final[f'ch{i}_green'].values.astype(int)
                raw_b = df_final[f'ch{i}_blue'].values.astype(int)

                render_data['r'][indices] = color_calibration.r_lut[raw_r]
                render_data['g'][indices] = color_calibration.g_lut[raw_g]
                render_data['b'][indices] = color_calibration.b_lut[raw_b]

            brect = QRectF(df_final['frame_time_ms'].min(), -0.5, 
                        (df_final['frame_time_ms'] + df_final['width']).max() - df_final['frame_time_ms'].min(), 10)
            
            # --- MODIFIED: 在发射信号时，传递 is_raw_data 标志 ---
            self.finished.emit(render_data, brect, is_raw_data)

        except Exception as e:
            import traceback
            print(f"RenderWorker error: {e}\n{traceback.format_exc()}")
            self.finished.emit({}, QRectF(), False)
        finally:
            self.is_running = False

    def _aggregate_data(self, df, num_bins, full_df):
        """
        数据聚合 V6.1 - 修正了所有返回路径，确保返回 (DataFrame, bool) 元组。
        """
        if df.empty or num_bins <= 0:
            # --- FIX: 确保返回元组 ---
            return pd.DataFrame(), False
        
        n_visible = len(df)
        
        # 1. 精细视图逻辑
        if num_bins >= n_visible:
            df_agg = df.copy()
            widths = df_agg['frame_time_ms'].diff().shift(-1)
            if len(widths) > 0:
                last_time = df_agg['frame_time_ms'].iloc[-1]
                next_point_series = full_df[full_df['frame_time_ms'] > last_time]
                if not next_point_series.empty:
                    widths.iloc[-1] = next_point_series['frame_time_ms'].iloc[0] - last_time
                else:
                    median_width = full_df['frame_time_ms'].diff().median()
                    widths.iloc[-1] = median_width if pd.notna(median_width) else 50.0
            
            default_width = 50.0
            df_agg['width'] = widths.fillna(default_width)
            # --- FIX: 确保返回元组 ---
            return df_agg, True

        # --- 2. 核心聚合逻辑 ---
        df = df.copy()
        df['importance_score'] = self._calculate_frame_importance_vectorized(df)
        
        min_time, max_time = df['frame_time_ms'].min(), df['frame_time_ms'].max()
        if max_time <= min_time:
            # --- FIX: 确保返回元组 ---
            return df.head(1), True
            
        bins = np.linspace(min_time, max_time, num_bins + 1)
        
        df['time_bin'] = pd.cut(df['frame_time_ms'], bins=bins, labels=False, right=False, include_lowest=True).values
        
        if df['time_bin'].isna().any():
            df.dropna(subset=['time_bin'], inplace=True)
            df['time_bin'] = df['time_bin'].astype(int)

        most_important_indices = df.loc[df.groupby('time_bin')['importance_score'].idxmax()].index
        bin_to_frame_map = pd.Series(most_important_indices, index=df.loc[most_important_indices, 'time_bin'])

        aggregated_blocks = []
        last_frame_index = -1

        for i in range(num_bins):
            if i in bin_to_frame_map and bin_to_frame_map[i] != last_frame_index:
                current_frame_index = bin_to_frame_map[i]
                new_block_start_frame = df.loc[current_frame_index].copy()
                new_block_start_frame['frame_time_ms'] = bins[i]
                aggregated_blocks.append(new_block_start_frame)
                last_frame_index = current_frame_index

        if not aggregated_blocks:
            if not df.empty:
                first_block = df.iloc[0].copy()
                first_block['frame_time_ms'] = min_time
                aggregated_blocks.append(first_block)
            else:
                # --- FIX: 确保返回元组 ---
                return pd.DataFrame(), False

        # --- 3. 计算宽度 ---
        df_agg = pd.DataFrame(aggregated_blocks).reset_index(drop=True)
        widths = df_agg['frame_time_ms'].diff().shift(-1)
        if len(widths) > 0:
            widths.iloc[-1] = max_time - df_agg['frame_time_ms'].iloc[-1]
        df_agg['width'] = widths.fillna(max_time - min_time)
        
        # --- FIX: 确保返回元组 ---
        return df_agg, False

    def _calculate_frame_importance_vectorized(self, df):
        """
        计算每帧重要性评分的向量化版本 - 性能极高。
        """
        if df.empty:
            return pd.Series([], dtype=np.float32)

        # --- 0. 初始化 ---
        scores = pd.Series(0, index=df.index, dtype=np.float32)
        
        # --- 1. 黑帧检测 (最高优先级) ---
        rgb_cols = [f'ch{i}_{c}' for i in range(10) for c in ['red', 'green', 'blue']]
        total_brightness = df[rgb_cols].sum(axis=1)
        
        is_blackout = total_brightness == 0
        scores[is_blackout] = 1000.0

        # --- 2. 基础亮度评分 (低优先级) ---
        base_brightness_score = np.minimum(99.0, total_brightness / 4.5)
        # +++ FIX: 显式转换为 float32 以匹配 scores 的 dtype +++
        scores[~is_blackout] += base_brightness_score[~is_blackout].astype(np.float32)

        # --- 3. 亮度跳变检测 (中优先级) ---
        prev_brightness = total_brightness.shift(1).fillna(total_brightness)
        next_brightness = total_brightness.shift(-1).fillna(total_brightness)
        
        jump_to_prev = (total_brightness - prev_brightness).abs()
        jump_to_next = (total_brightness - next_brightness).abs()
        
        max_brightness_jump = np.maximum(jump_to_prev, jump_to_next)
        
        brightness_jump_score = np.minimum(100.0, max_brightness_jump / 4.5)
        # +++ FIX: 显式转换为 float32 +++
        scores += brightness_jump_score.astype(np.float32)

        # --- 4. 变色帧检测 (高优先级) ---
        total_color_distance_prev = pd.Series(0, index=df.index, dtype=np.float32)
        total_color_distance_next = pd.Series(0, index=df.index, dtype=np.float32)

        for i in range(10):
            r_col, g_col, b_col = f'ch{i}_red', f'ch{i}_green', f'ch{i}_blue'
            
            # 与前一帧的差异
            dr_p = df[r_col] - df[r_col].shift(1)
            dg_p = df[g_col] - df[g_col].shift(1)
            db_p = df[b_col] - df[b_col].shift(1)
            dist_sq_p = dr_p**2 + dg_p**2 + db_p**2
            # +++ FIX: 显式转换为 float32 +++
            total_color_distance_prev += np.sqrt(dist_sq_p).astype(np.float32)

            # 与后一帧的差异
            dr_n = df[r_col] - df[r_col].shift(-1)
            dg_n = df[g_col] - df[g_col].shift(-1)
            db_n = df[b_col] - df[b_col].shift(-1)
            dist_sq_n = dr_n**2 + dg_n**2 + db_n**2
            # +++ FIX: 显式转换为 float32 +++
            total_color_distance_next += np.sqrt(dist_sq_n).astype(np.float32)

        total_color_distance_prev = total_color_distance_prev.fillna(0)
        total_color_distance_next = total_color_distance_next.fillna(0)

        max_color_change = np.maximum(total_color_distance_prev, total_color_distance_next)
        
        color_change_score = np.minimum(500.0, max_color_change * 2)
        # +++ FIX: 显式转换为 float32 (尽管 max_color_change 已经是 float32, 但这样做更安全) +++
        scores += color_change_score.astype(np.float32)
        
        return scores

class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        # 您的代码逻辑只用到了 values，所以 scale 和 spacing 参数可以忽略，但必须存在于方法签名中
        return [f"{int(v // 3600000):02d}:{int((v / 60000) % 60):02d}:{int((v / 1000) % 60):02d}.{int(v % 1000):03d}" for v in values]

class FastScatterItem(pg.GraphicsObject):
    """
    高性能散点图项 - 统一矩形渲染
    """
    def __init__(self):
        super().__init__()
        self.data = None
        self.pen = pg.mkPen(color=(80, 80, 80), width=0.5) # 更细的笔，在大视图下效果更好
        self._boundingRect = QRectF()

    def setData(self, data, boundingRect):
        self.data = data
        self._boundingRect = boundingRect
        self.prepareGeometryChange()
        self.update()

    def clear(self):
        self.setData(None, QRectF())

    def paint(self, painter, option, widget):
        if self.data is None or len(self.data['x']) == 0:
            return

        painter.save()
        try:
            frame_pen = pg.mkPen(color=(0, 0, 0), width=1, style=Qt.DashDotDotLine)
            # 遍历所有要绘制的点 (每个点代表一个通道的一个矩形)
            for i in range(len(self.data['x'])):
                # 直接使用 QColor 效率更高
                painter.setBrush(QColor(self.data['r'][i], self.data['g'][i], self.data['b'][i]))

                # 1. 先绘制一个没有边框的填充矩形
                painter.setPen(Qt.NoPen)
                rect = QRectF(self.data['x'][i], self.data['y'][i] - 0.5, self.data['w'][i], 1.0)
                painter.drawRect(rect)

                # 2. 再使用画笔单独绘制这个矩形的左边框
                painter.setPen(frame_pen)
                # 获取矩形的左上角和左下角坐标
                p1 = rect.topLeft()
                p2 = rect.bottomLeft()
                painter.drawLine(p1, p2)
        finally:
            painter.restore()

    def boundingRect(self):
        return self._boundingRect

class IDXIndicatorsItem(pg.GraphicsObject):
    """
    用于在IDX通道显示播放头、选区和数据帧指示器的统一图形项。
    """
    def __init__(self):
        super().__init__()
        self.playback_head_pos = None
        self.region_start = None
        self.region_end = None
        self.frame_positions = None # 新增：存储数据帧位置
        
        self.playback_brush = pg.mkBrush(255, 0, 0)
        self.region_brush = pg.mkBrush(0, 0, 255, 150)
        self.frame_brush = pg.mkBrush(50, 50, 50) # 新增：用于数据帧的深灰色笔刷
        self.no_pen = pg.mkPen(None)

    def setPlaybackHead(self, pos):
        self.playback_head_pos = pos
        self.update()

    def setRegion(self, start, end):
        self.region_start = start
        self.region_end = end
        self.update()

    def setFramePositions(self, positions):
        """新增：设置数据帧位置并触发重绘"""
        self.frame_positions = positions
        self.update()

    def clear(self):
        self.playback_head_pos = None
        self.region_start = None
        self.region_end = None
        self.frame_positions = None # 新增：同时清除数据帧位置
        self.update()

    def paint(self, painter, option, widget):
        transform = self.deviceTransform()
        if transform is None:
            return

        painter.save()
        try:
            painter.setPen(self.no_pen)

            # --- 1. 绘制播放头指示器 (红色三角形) ---
            if self.playback_head_pos is not None:
                painter.setBrush(self.playback_brush)
                pixel_pos = transform.map(QPointF(self.playback_head_pos, -1.0))
                pixel_triangle = QPolygonF([
                    pixel_pos,
                    pixel_pos + QPointF(-5, -8),
                    pixel_pos + QPointF(5, -8),
                ])
                painter.drawPolygon(transform.inverted()[0].map(pixel_triangle))

            # --- 2. 绘制选区指示器 (蓝色"旗帜") ---
            if self.region_start is not None and self.region_end is not None:
                painter.setBrush(self.region_brush)

                start_pixel_pos = transform.map(QPointF(self.region_start, -1.0))
                start_flag = QPolygonF([
                    start_pixel_pos,
                    start_pixel_pos + QPointF(0, -8),
                    start_pixel_pos + QPointF(8, -8),
                    start_pixel_pos + QPointF(8, -5),
                ])
                painter.drawPolygon(transform.inverted()[0].map(start_flag))

                end_pixel_pos = transform.map(QPointF(self.region_end, -1.0))
                end_flag = QPolygonF([
                    end_pixel_pos,
                    end_pixel_pos + QPointF(0, -8),
                    end_pixel_pos + QPointF(-8, -8),
                    end_pixel_pos + QPointF(-8, -5),
                ])
                painter.drawPolygon(transform.inverted()[0].map(end_flag))

            # --- 3. 新增：绘制数据帧指示器 (深灰色菱形) ---
            if self.frame_positions is not None:
                painter.setBrush(self.frame_brush)
                for x_pos in self.frame_positions:
                    # 将菱形的中心点（逻辑坐标）映射到像素坐标
                    pixel_pos = transform.map(QPointF(x_pos, -1.0))
                    # 在像素坐标系中定义一个小菱形的形状
                    pixel_diamond = QPolygonF([
                        pixel_pos + QPointF(0, -3),  # 顶点
                        pixel_pos + QPointF(3, 0),   # 右点
                        pixel_pos + QPointF(0, 3),   # 底点
                        pixel_pos + QPointF(-3, 0),  # 左点
                    ])
                    # 将像素坐标的菱形转换回逻辑坐标系进行绘制，以确保其大小在屏幕上保持不变
                    painter.drawPolygon(transform.inverted()[0].map(pixel_diamond))
        finally:
            painter.restore()

    def boundingRect(self):
        # 返回一个在水平方向上足够大的矩形，覆盖约2.7小时的时间范围
        return QRectF(-1e7, -1.5, 2e7, 1.0)

class MarkerItem(pg.GraphicsObject):
    """
    一个自定义的、类似 Adobe Premiere Pro 的标记图形项。
    它包含一个"房子"形状的头部、文本标签和一条垂直延伸线。
    """
    def __init__(self, pos, text, color=QColor(60, 180, 75), timeline_widget=None):
        super().__init__()
        
        self.marker_text = text
        self.marker_color = color
        self.timeline_widget = timeline_widget  # 添加对时间轴组件的引用
        
        # 定义头部尺寸（单位：像素）
        self.head_width = 14
        self.head_height = 10 # 矩形部分的高度
        self.roof_height = 6  # 三角形部分的高度
        
        self.line_pen = pg.mkPen(color=color, width=1, style=Qt.DashLine)
        self.fill_brush = pg.mkBrush(color)
        self.outline_pen = pg.mkPen(color='k', width=1)

        # 将标记的"基座"放在MARK通道的中心线上 (y=10)
        self.setPos(pos, 10)
        
        # 启用鼠标事件
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def paint(self, painter, option, widget):
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing)

            # --- 1. 绘制从基座向下延伸的垂直线 (在数据坐标系中) ---
            painter.setPen(self.line_pen)
            # 从本地坐标(0,0)即y=10，向下绘制到y=0 (CH0中心)
            painter.drawLine(QPointF(0, 0), QPointF(0, -10))

            # --- 2. 采用像素坐标系绘制大小固定的、尖顶朝下的标记头 ---
            transform = self.deviceTransform()
            if transform is None:
                return

            pixel_origin = transform.map(QPointF(0, 0))
            pixel_path = QPainterPath()

            # a. 绘制矩形部分 (在基座上方)
            #    注意：屏幕坐标系Y轴向下为正，所以向上是负值
            rect = QRectF(
                pixel_origin.x() - self.head_width / 2,
                pixel_origin.y() - self.head_height, # 从基座向上绘制
                self.head_width,
                self.head_height
            )
            pixel_path.addRect(rect)

            # b. 绘制三角形部分 (在基座下方，尖顶朝下)
            poly = QPolygonF([
                QPointF(pixel_origin.x() - self.head_width / 2, pixel_origin.y()), # 左上角
                QPointF(pixel_origin.x() + self.head_width / 2, pixel_origin.y()), # 右上角
                QPointF(pixel_origin.x(), pixel_origin.y() + self.roof_height)     # 向下的顶点
            ])
            pixel_path.addPolygon(poly)

            # c. 将像素路径转换回视图坐标系进行绘制
            painter.setPen(self.outline_pen)
            painter.setBrush(self.fill_brush)
            painter.drawPath(transform.inverted()[0].map(pixel_path))
        finally:
            painter.restore()

    def boundingRect(self):
        # 修正：垂直线从 0 向下延伸到 -10，头部在 0 附近
        # X轴给点宽度(-1, 1)，Y轴必须覆盖整个绘制范围 [-10.5, 1.5]
        return QRectF(-1, -1, 2, 12)

    def mouseDoubleClickEvent(self, event):
        """处理双击事件，定位到标记位置并弹出对话框让用户编辑标记文本"""
        if self.timeline_widget is not None:
            # 获取当前标记的时间位置
            pos = self.pos()
            time_ms = pos.x()

            # 定位播放头到标记位置
            self.timeline_widget.set_playback_head_time(time_ms)

            # 弹出输入对话框让用户修改标记文本
            from PySide6.QtWidgets import QInputDialog
            new_text, ok = QInputDialog.getText(
                self.timeline_widget,
                "Edit Marker",
                "Marker Name:",
                text=self.marker_text
            )

            if ok and new_text:
                # 更新标记文本
                self.marker_text = new_text
                # 发射信号更新标记
                self.timeline_widget.update_marker_requested.emit(time_ms, new_text)
                # 触发重绘
                self.update()
        event.accept()

class TimelineWidget(pg.PlotWidget):
    # --- SIGNALS ---
    region_selected = Signal(float, float)
    playback_head_changed = Signal(float)
    render_request = Signal(pd.DataFrame, tuple, float, int)
    offset_requested = Signal(float, float, float)
    # Signals for keyboard shortcuts
    insert_blackout_requested = Signal(float)
    insert_color_frame_requested = Signal(float, dict, int, str)
    insert_color_dialog_requested = Signal(float)
    add_marker_requested = Signal(float, str)
    # Signals for copy/paste operations - now include timeline_type
    cut_requested = Signal(float, float, str)   # start_ms, end_ms, timeline_type
    copy_requested = Signal(float, float, str)  # start_ms, end_ms, timeline_type
    paste_requested = Signal(float, str)        # at_ms, timeline_type
    delete_requested = Signal(float, float, str) # start_ms, end_ms, timeline_type
    # Signal for updating marker
    update_marker_requested = Signal(float, str)
    # Signal for audio vertical zoom (Alt+Wheel)
    audio_vertical_zoom_requested = Signal(float)

    # --- CONSTANTS ---
    MARKER_TEXT_VISIBILITY_THRESHOLD = 0.0005
    TIMELINE_Y_RANGE = (-1.5, 10.5)  # 修改：优化显示效果

    def __init__(self, parent=None, timeline_type='edit'):
        self.axis = TimeAxisItem(orientation='bottom')
        super().__init__(parent=parent, axisItems={'bottom': self.axis})
        self.timeline_type = timeline_type # 'source' 或 'edit'
        self.plot_item = self.getPlotItem()
        
        # --- Basic Setup ---
        self.plot_item.hideButtons()
        self.setBackground('w')
        self.plot_item.setLabel('bottom', '时间')
        self.plot_item.showGrid(x=True, y=True, alpha=0.2)
        
        # --- Y-Axis Setup ---
        y_axis = self.plot_item.getAxis('left')
        y_axis.setLabel('通道')
        y_axis.setWidth(70)
        y_axis.setStyle(autoExpandTextSpace=False)
        new_ticks = [[(i, f"CH{i}") for i in range(10)]]
        new_ticks[0].extend([(10, "MARK"), (-1, "IDX")])
        y_axis.setTicks(new_ticks)
        self.plot_item.setYRange(*self.TIMELINE_Y_RANGE, padding=0)
        self.plot_item.layout.setContentsMargins(0, 0, 0, 0)
        
        # [修改] 彻底禁用 X 和 Y 轴的自动缩放
        self.plot_item.vb.disableAutoRange(axis=pg.ViewBox.YAxis)
        self.plot_item.vb.disableAutoRange(axis=pg.ViewBox.XAxis)

        # Disable default mouse interactions to prevent conflicts with ToolManager
        self.plot_item.setMouseEnabled(x=False, y=False)

        # 禁用右键菜单
        self.plot_item.vb.setMenuEnabled(False)
        
        # --- Plot Items ---
        self.playback_head = pg.InfiniteLine(pos=0, angle=90, movable=True, pen=pg.mkPen('r', width=2))
        self.playback_head.setHoverPen(pg.mkPen('r', width=4))
        self.region_item = pg.LinearRegionItem(orientation='vertical', brush=pg.mkBrush(0, 0, 255, 40))
        self.scatter_item = FastScatterItem()
        self.idx_indicators_item = IDXIndicatorsItem()
        self.ghost_region_item = pg.LinearRegionItem(orientation='vertical', brush=pg.mkBrush(100, 100, 255, 70))
        self.ghost_region_item.setZValue(-2)
        self.ghost_region_item.hide()
        self.zoom_label = pg.TextItem(text="100%", color=(0, 0, 0), anchor=(1, 0))
        self.zoom_label.setZValue(100)

        # [修改] 使用 QLabel 作为偏移提示，而不是 pg.LabelItem
        self.offset_label = QLabel(self)
        self.offset_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: white;
            padding: 5px;
            border-radius: 4px;
            font-family: Arial;
            font-size: 10pt;
        """
        )
        self.offset_label.setAttribute(Qt.WA_TranslucentBackground)
        self.offset_label.hide()

        self.marker_items = []
        self.marker_text_items = []

        # --- Add Items to Plot ---
        for item in [self.scatter_item, self.idx_indicators_item, self.playback_head,
                     self.region_item, self.ghost_region_item, self.zoom_label]:
            self.plot_item.addItem(item)
        
        # --- Z-Values ---
        self.region_item.setZValue(-1)
        self.scatter_item.setZValue(1)
        self.idx_indicators_item.setZValue(5)
        self.playback_head.setZValue(10)

        # ... (其余 __init__ 内容保持不变)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.last_mouse_pos = None
        self.current_data = pd.DataFrame()
        self.render_thread = QThread()
        self.render_worker = RenderWorker()
        self.render_worker.moveToThread(self.render_thread)
        self.render_request.connect(self.render_worker.process_data)
        self.render_worker.finished.connect(self._on_render_finished)
        self.render_thread.start()
        self.playback_head.sigPositionChanged.connect(self._update_idx_indicators)
        self.region_item.sigRegionChanged.connect(self._update_idx_indicators)
        self.plot_item.vb.sigRangeChanged.connect(self.on_viewport_changed)
        self.viewport_change_timer = QTimer()
        self.viewport_change_timer.setSingleShot(True)
        self.viewport_change_timer.timeout.connect(self._request_render_in_background)
        self.drag_start_pos = None
        self.drag_offset = 0
        self.min_zoom_range = 100  # Minimum visible range in ms
        self.max_zoom_range = 1e8  # Maximum visible range in ms

        # Initialize Tool Manager for mouse interaction
        self.tool_manager = ToolManager(self)

    # [修改] mouseReleaseEvent 方法，委托给 ToolManager
    def mouseReleaseEvent(self, event):
        viewbox_pos = self.plot_item.vb.mapFromParent(event.position())
        pos = self.plot_item.vb.mapToView(viewbox_pos)
        if self.tool_manager.on_mouse_release(event, pos):
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        modifiers = event.modifiers()

        if modifiers == Qt.ControlModifier:
            # Ctrl+Wheel: Zoom centered on mouse
            mouse_point = self.plot_item.vb.mapSceneToView(event.scenePosition())
            current_range = self.plot_item.viewRange()[0]
            current_width = current_range[1] - current_range[0]

            # Calculate zoom factor
            zoom_factor = 0.8 if delta > 0 else 1.25
            new_width = current_width * zoom_factor

            # 获取音频数据的总时长用于ZOOM OUT钳位（而不是当前显示范围）
            audio_duration = None
            try:
                main_window = self.window()
                if hasattr(main_window, 'source_audio_track') and hasattr(main_window, 'edit_audio_track'):
                    if self.timeline_type == 'source' and main_window.source_audio_track.isVisible():
                        audio_data = main_window.source_audio_track.audio_viz_item.audio_data
                        if audio_data is not None:
                            audio_duration = audio_data.duration_ms
                    elif self.timeline_type == 'edit' and main_window.edit_audio_track.isVisible():
                        audio_data = main_window.edit_audio_track.audio_viz_item.audio_data
                        if audio_data is not None:
                            audio_duration = audio_data.duration_ms
            except:
                pass

            # Apply zoom limits
            # ZOOM OUT 钳位：不允许灯光轨道缩放范围超过音频数据的总时长
            effective_max_zoom = self.max_zoom_range
            if audio_duration is not None:
                effective_max_zoom = min(self.max_zoom_range, audio_duration)

            if new_width < self.min_zoom_range:
                new_width = self.min_zoom_range
            elif new_width > effective_max_zoom:
                new_width = effective_max_zoom

            # Calculate new range centered on mouse position
            mouse_x = mouse_point.x()
            ratio = (mouse_x - current_range[0]) / current_width if current_width > 0 else 0.5
            new_start = mouse_x - new_width * ratio
            new_end = new_start + new_width
            self.plot_item.setXRange(new_start, new_end, padding=0)
            event.accept()
        elif modifiers == Qt.ShiftModifier:
            # Shift+Wheel: Fast horizontal scroll (10x speed)
            scroll_amount = (delta / 120) * 1000  # 1000ms per scroll step
            current_range = self.plot_item.viewRange()[0]
            self.plot_item.setXRange(current_range[0] - scroll_amount, current_range[1] - scroll_amount, padding=0)
            event.accept()
        elif modifiers == Qt.AltModifier:
            # Per PRD 3.1: Alt+Wheel - Vertical Zoom (Audio Frequency)
            # Emit signal to let TimelineGroupWidget handle audio track zoom
            self.audio_vertical_zoom_requested.emit(delta)
            event.accept()
        elif modifiers == Qt.NoModifier:
            # Wheel: Normal horizontal scroll
            scroll_amount = (delta / 120) * 100  # 100ms per scroll step
            current_range = self.plot_item.viewRange()[0]
            self.plot_item.setXRange(current_range[0] - scroll_amount, current_range[1] - scroll_amount, padding=0)
            event.accept()
        else:
            super().wheelEvent(event)

    def set_data(self, df: pd.DataFrame, auto_zoom: bool = True):
        perf_monitor.start_timing(f"TimelineWidget.set_data ({len(df)}帧)")
        self.current_data = df.copy() if not df.empty else pd.DataFrame()
        if df.empty: 
            self.scatter_item.clear()
            self.show_markers(df)
            perf_monitor.end_timing(f"TimelineWidget.set_data ({len(df)}帧)", "- 空数据集")
            return
        self._request_render_in_background()
        self.show_markers(df)
        if auto_zoom and not df.empty:
            min_time = df['frame_time_ms'].min()
            max_time = df['frame_time_ms'].max()
            self.plot_item.setXRange(min_time, max_time, padding=0.05)
        perf_monitor.end_timing(f"TimelineWidget.set_data ({len(df)}帧)")

    def keyPressEvent(self, event):
        # 空格键：优先传递给父窗口处理视频播放/暂停
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            # 不再使用空格作为临时平移模式，而是传递给MainWindow处理视频播放
            event.ignore()  # 让事件向上传递到MainWindow
            return

        # 源时间轴权限检查
        if self.timeline_type == 'source':
            # 只允许选区导航和复制操作，其他操作不允许
            allowed_keys = [Qt.Key_Left, Qt.Key_Right, Qt.Key_C, Qt.Key_J, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Plus, Qt.Key_Minus]
            if event.key() not in allowed_keys:
                # 显示提示信息
                return

        current_time = self.get_playback_head_time()
        modifiers = event.modifiers()
        key = event.key()
        new_time = -1

        # Per PRD 4.1: Navigation keys
        if key == Qt.Key_Left:
            if modifiers == Qt.ShiftModifier:
                new_time = current_time - 100  # Shift+Left: ±100ms
            elif modifiers == Qt.AltModifier:
                new_time = self._jump_to_prev_marker(current_time)  # Alt+Left: Prev Marker
            else:
                new_time = current_time - 10  # Left: ±10ms
        elif key == Qt.Key_Right:
            if modifiers == Qt.ShiftModifier:
                new_time = current_time + 100  # Shift+Right: ±100ms
            elif modifiers == Qt.AltModifier:
                new_time = self._jump_to_next_marker(current_time)  # Alt+Right: Next Marker
            else:
                new_time = current_time + 10  # Right: ±10ms
        elif key == Qt.Key_Home:
            if not self.current_data.empty:
                new_time = self.current_data['frame_time_ms'].min()
        elif key == Qt.Key_End:
            if not self.current_data.empty:
                new_time = self.current_data['frame_time_ms'].max()
        elif key == Qt.Key_PageUp:
            view_range = self.plot_item.viewRange()[0]
            view_width = view_range[1] - view_range[0]
            new_time = current_time - view_width * 0.5
        elif key == Qt.Key_PageDown:
            view_range = self.plot_item.viewRange()[0]
            view_width = view_range[1] - view_range[0]
            new_time = current_time + view_width * 0.5
        elif key == Qt.Key_Plus or key == Qt.Key_Equal:
            # Zoom in - 使用带钳位的缩放
            self._apply_clamped_zoom(0.8)
        elif key == Qt.Key_Minus:
            # Zoom out - 使用带钳位的缩放
            self._apply_clamped_zoom(1.25)
        elif key == Qt.Key_J:
            if self.last_mouse_pos:
                viewbox_pos = self.plot_item.vb.mapFromParent(self.last_mouse_pos)
                time_pos = self.plot_item.vb.mapToView(viewbox_pos)
                new_time = time_pos.x()
        # Operation keys - add timeline type to signals
        elif key == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            # Ctrl+C 复制 - 两种时间轴都支持
            start_ms, end_ms = self.get_selected_region()
            if abs(end_ms - start_ms) > 1:
                self.copy_requested.emit(start_ms, end_ms, self.timeline_type)
        elif key == Qt.Key_X and event.modifiers() == Qt.ControlModifier:
            # Ctrl+X 剪切 - 仅编辑时间轴支持
            if self.timeline_type == 'edit':
                start_ms, end_ms = self.get_selected_region()
                if abs(end_ms - start_ms) > 1:
                    self.cut_requested.emit(start_ms, end_ms, self.timeline_type)
            else:
                # 源时间轴不支持剪切，显示提示
                # Note: This would require a status bar or some way to show messages
                pass
        elif key == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            # Ctrl+V 粘贴 - 仅编辑时间轴支持
            if self.timeline_type == 'edit':
                self.paste_requested.emit(self.get_playback_head_time(), self.timeline_type)
            else:
                # 源时间轴不支持粘贴，显示提示
                # Note: This would require a status bar or some way to show messages
                pass
        elif key == Qt.Key_Delete:
            # Delete 删除 - 仅编辑时间轴支持
            if self.timeline_type == 'edit':
                start_ms, end_ms = self.get_selected_region()
                if abs(end_ms - start_ms) > 1:
                    self.delete_requested.emit(start_ms, end_ms, self.timeline_type)
            else:
                # 源时间轴不支持删除，显示提示
                # Note: This would require a status bar or some way to show messages
                pass
        # Insert frame shortcuts
        elif key == Qt.Key_B:
            # Insert blackout frame at current playback head
            self.insert_blackout_requested.emit(current_time)
        elif key == Qt.Key_W:
            # Insert white frame at current playback head
            self.insert_color_frame_requested.emit(current_time, {'r': 15, 'g': 15, 'b': 15}, 0, "")
        elif key == Qt.Key_R:
            # Insert red frame at current playback head
            self.insert_color_frame_requested.emit(current_time, {'r': 15, 'g': 0, 'b': 0}, 0, "")
        elif key == Qt.Key_G:
            # Insert green frame at current playback head
            self.insert_color_frame_requested.emit(current_time, {'r': 0, 'g': 15, 'b': 0}, 0, "")
        elif key == Qt.Key_B and event.modifiers() == Qt.ControlModifier:
            # Ctrl+B might be for another function, so we'll keep the blackout shortcut as just 'B'
            self.insert_blackout_requested.emit(current_time)
        elif key == Qt.Key_I:
            # Insert custom color frame (show dialog)
            self.insert_color_dialog_requested.emit(current_time)
        elif key == Qt.Key_M:
            # Add marker at current playback head - show input dialog
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "Add Marker", "Marker Name:")
            if ok and name:
                self.add_marker_requested.emit(current_time, name)
        # Per PRD 4.3: Selection & View shortcuts
        elif key == Qt.Key_A and modifiers == Qt.ControlModifier:
            # Ctrl+A: Select All
            if not self.current_data.empty:
                min_t = self.current_data['frame_time_ms'].min()
                max_t = self.current_data['frame_time_ms'].max()
                self.region_item.setRegion([min_t, max_t])
        elif key == Qt.Key_D and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            # Ctrl+Shift+D: Deselect
            self.region_item.setRegion([0, 0])
        elif key == Qt.Key_Backslash:
            # \: Fit to View
            self._fit_to_view()
        # Offset shortcuts
        elif key == Qt.Key_BracketLeft and modifiers == Qt.ControlModifier:
            # Ctrl+[ : Quick offset left by 100ms
            self.apply_quick_offset(-100)
        elif key == Qt.Key_BracketRight and event.modifiers() == Qt.ControlModifier:
            # Ctrl+] : Quick offset right by 100ms
            self.apply_quick_offset(100)
        else:
            super().keyPressEvent(event)
            return
            
        if new_time >= 0:
            self.set_playback_head_time(new_time)
        event.accept()

    def keyReleaseEvent(self, event):
        # 空格键释放：同样传递给父窗口
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            event.ignore()  # 让事件向上传递
            return
        super().keyReleaseEvent(event)

    def _jump_to_prev_marker(self, current_time: float) -> float:
        """Per PRD 4.1: Jump to previous marker"""
        if self.current_data.empty or 'marker' not in self.current_data.columns:
            return current_time
        markers = self.current_data[self.current_data['marker'].notna() & (self.current_data['marker'] != '')]
        if markers.empty:
            return current_time
        prev_markers = markers[markers['frame_time_ms'] < current_time - 1]
        if prev_markers.empty:
            return current_time
        return prev_markers['frame_time_ms'].max()

    def _jump_to_next_marker(self, current_time: float) -> float:
        """Per PRD 4.1: Jump to next marker"""
        if self.current_data.empty or 'marker' not in self.current_data.columns:
            return current_time
        markers = self.current_data[self.current_data['marker'].notna() & (self.current_data['marker'] != '')]
        if markers.empty:
            return current_time
        next_markers = markers[markers['frame_time_ms'] > current_time + 1]
        if next_markers.empty:
            return current_time
        return next_markers['frame_time_ms'].min()

    def _fit_to_view(self):
        """Per PRD 4.3: Fit all data to view"""
        if self.current_data.empty:
            return
        min_t = self.current_data['frame_time_ms'].min()
        max_t = self.current_data['frame_time_ms'].max()
        self.plot_item.setXRange(min_t, max_t, padding=0.05)

    def _apply_clamped_zoom(self, zoom_factor: float):
        """应用带钳位的缩放，zoom_factor < 1 为放大，> 1 为缩小"""
        current_range = self.plot_item.viewRange()[0]
        current_width = current_range[1] - current_range[0]
        new_width = current_width * zoom_factor

        # 获取音频数据的总时长用于ZOOM OUT钳位
        audio_duration = None
        try:
            main_window = self.window()
            if hasattr(main_window, 'source_audio_track') and hasattr(main_window, 'edit_audio_track'):
                if self.timeline_type == 'source' and main_window.source_audio_track.isVisible():
                    audio_data = main_window.source_audio_track.audio_viz_item.audio_data
                    if audio_data is not None:
                        audio_duration = audio_data.duration_ms
                elif self.timeline_type == 'edit' and main_window.edit_audio_track.isVisible():
                    audio_data = main_window.edit_audio_track.audio_viz_item.audio_data
                    if audio_data is not None:
                        audio_duration = audio_data.duration_ms
        except:
            pass

        # Apply zoom limits
        effective_max_zoom = self.max_zoom_range
        if audio_duration is not None:
            effective_max_zoom = min(self.max_zoom_range, audio_duration)

        if new_width < self.min_zoom_range:
            new_width = self.min_zoom_range
        elif new_width > effective_max_zoom:
            new_width = effective_max_zoom

        # 以当前视图中心为缩放中心
        center = (current_range[0] + current_range[1]) / 2
        new_start = center - new_width / 2
        new_end = center + new_width / 2
        self.plot_item.setXRange(new_start, new_end, padding=0)

    def _update_marker_text_visibility(self):
        if not self.marker_items: return
        view_range = self.plot_item.viewRange()[0]
        view_width_ms = view_range[1] - view_range[0]
        if view_width_ms <= 0: return
        pixels_per_ms = self.plot_item.vb.width() / view_width_ms
        show_text = bool(pixels_per_ms > self.MARKER_TEXT_VISIBILITY_THRESHOLD)
        for marker_graphic, text_item in zip(self.marker_items, self.marker_text_items):
            text_item.setVisible(show_text)
            if show_text:
                graphic_pos = marker_graphic.pos()
                text_y_pos = 10
                pixel_pos = self.plot_item.vb.mapViewToDevice(graphic_pos)
                pixel_pos.setX(pixel_pos.x() + marker_graphic.head_width / 2 + 5)
                view_pos = self.plot_item.vb.mapDeviceToView(pixel_pos)
                text_item.setPos(view_pos.x(), text_y_pos)

    def shutdown(self):
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.quit()
            self.render_thread.wait(2000)

    def on_viewport_changed(self):
        if self.current_data.empty: return
        # 所有的 UI 更新都由定时器统一触发，避免在信号回调中直接修改坐标
        self.viewport_change_timer.start(10)

    def _request_render_in_background(self):
        if self.current_data.empty:
            self.scatter_item.clear()
            return

        # 1. 更新缩放百分比标签和标记文字可见性
        self.update_zoom_label()
        self._update_marker_text_visibility()

        # 2. 发起后台渲染请求
        df_copy = self.current_data.copy()
        view_range = self.plot_item.viewRange()[0]
        view_width_pixels = self.plot_item.vb.width()
        self.render_request.emit(df_copy, view_range, view_width_pixels, 10)

    @pyqtSlot(dict, QRectF, bool)
    def _on_render_finished(self, render_data, brect, is_raw_data):
        if not render_data or len(render_data['x']) == 0:
            self.scatter_item.clear()
            self.idx_indicators_item.setFramePositions(None)
        else:
            self.scatter_item.setData(render_data, brect)
            if is_raw_data:
                self.idx_indicators_item.setFramePositions(np.unique(render_data['x']))
            else:
                self.idx_indicators_item.setFramePositions(None)

    def _update_idx_indicators(self):
        self.idx_indicators_item.setPlaybackHead(self.playback_head.value())
        self.idx_indicators_item.setRegion(*self.region_item.getRegion())

    def show_markers(self, df: pd.DataFrame):
        for item in self.marker_items + self.marker_text_items:
            self.plot_item.removeItem(item)
        self.marker_items.clear()
        self.marker_text_items.clear()
        if df.empty: return
        markers_df = df[df['marker'].notna() & (df['marker'] != "")]
        colors = [QColor(60, 180, 75), QColor(255, 225, 25), QColor(0, 130, 200), QColor(245, 130, 48)]
        for i, (_, marker_row) in enumerate(markers_df.iterrows()):
            time_ms, text = marker_row['frame_time_ms'], marker_row['marker']
            color = colors[i % len(colors)]
            marker_item = MarkerItem(pos=time_ms, text=text, color=color, timeline_widget=self)
            marker_item.setZValue(6)
            self.plot_item.addItem(marker_item)
            self.marker_items.append(marker_item)
            text_item = pg.TextItem(text=text, color=color, anchor=(0, 0.5))
            text_item.setZValue(7)
            self.plot_item.addItem(text_item)
            self.marker_text_items.append(text_item)
        self._update_marker_text_visibility()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            viewbox_pos = self.plot_item.vb.mapFromParent(event.position())
            click_pos = self.plot_item.vb.mapToView(viewbox_pos)

            # 检查是否点击在 MarkerItem 上，如果是则直接调用其双击处理
            for marker_item in self.marker_items:
                marker_time = marker_item.pos().x()
                # 计算容差：使用较大的点击区域（20像素），转换为时间单位
                view_range = self.plot_item.viewRange()[0]
                view_width = view_range[1] - view_range[0]
                plot_width = self.plot_item.width()
                tolerance = 20 * view_width / plot_width if plot_width > 0 else 100
                if abs(click_pos.x() - marker_time) < tolerance:
                    # 直接调用 MarkerItem 的双击处理
                    marker_item.mouseDoubleClickEvent(event)
                    return

            # 双击其他区域不做任何操作，使用 F 键进行 fit
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Delegate mouse press to ToolManager."""
        viewbox_pos = self.plot_item.vb.mapFromParent(event.position())
        pos = self.plot_item.vb.mapToView(viewbox_pos)
        if self.tool_manager.on_mouse_press(event, pos):
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Delegate mouse move to ToolManager."""
        self.last_mouse_pos = event.position()
        viewbox_pos = self.plot_item.vb.mapFromParent(event.position())
        pos = self.plot_item.vb.mapToView(viewbox_pos)
        if self.tool_manager.on_mouse_move(event, pos):
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def show_offset_dialog(self):
        """Show offset dialog to get user input for offset amount."""
        if self.timeline_type == 'source':
            # Source timeline does not allow offset functionality
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "源时间轴不支持偏移操作")
            return
        
        from PySide6.QtWidgets import QInputDialog
        
        start_ms, end_ms = self.get_selected_region()
        if abs(end_ms - start_ms) <= 1:
            # If no selection, show message
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先选择一个时间区域")
            return
        
        # Get offset amount from user
        offset_ms, ok = QInputDialog.getDouble(
            self,
            "时间偏移",
            f"输入偏移量 (ms):\n当前选区: {start_ms:.1f} - {end_ms:.1f}",
            0.0,  # Default value
            -99999.0,  # Minimum value
            999999.0,   # Maximum value
            1  # Decimals
        )
        
        if ok and abs(offset_ms) > 0.01:  # If user confirmed and offset is meaningful
            self.offset_requested.emit(start_ms, end_ms, offset_ms)

    def apply_quick_offset(self, offset_ms):
        """Apply quick offset."""
        if self.timeline_type == 'source':
            # Source timeline does not allow offset functionality
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "源时间轴不支持偏移操作")
            return
        
        start_ms, end_ms = self.get_selected_region()
        if abs(end_ms - start_ms) > 1:
            self.offset_requested.emit(start_ms, end_ms, offset_ms)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先选择一个时间区域")

    def update_zoom_label(self):
        if self.current_data.empty:
            self.zoom_label.setText("100%")
            return
        view_range = self.plot_item.viewRange()
        x_min, x_max = view_range[0]
        view_width = x_max - x_min
        data_min = self.current_data['frame_time_ms'].min()
        data_max = self.current_data['frame_time_ms'].max()
        data_width = data_max - data_min
        if data_width <= 0:
            self.zoom_label.setText("100%")
            return
        zoom_ratio = 100 if view_width >= data_width else (data_width / view_width) * 100
        self.zoom_label.setText(f"{zoom_ratio:.0f}%")
        x_pos = view_range[0][1] - (view_range[0][1] - view_range[0][0]) * 0.02
        y_pos = view_range[1][0] + (view_range[1][1] - view_range[1][0]) * 0.02
        self.zoom_label.setPos(x_pos, y_pos)

    def on_region_changed(self): self.region_selected.emit(*self.region_item.getRegion())
    def on_playback_head_moved(self): self.playback_head_changed.emit(self.playback_head.value())

    def get_selected_region(self) -> tuple[float, float]: return self.region_item.getRegion()
    def get_playback_head_time(self) -> float: return self.playback_head.value()
    def set_playback_head_time(self, time_ms: float): self.playback_head.setValue(time_ms)
    def set_selected_region(self, start_ms: float, end_ms: float): self.region_item.setRegion([start_ms, end_ms])

    def snap_to_nearest_frame(self, time_ms: float, tolerance_ms: float = 50.0) -> float:
        """
        Per PRD 5.3: Find the nearest keyframe within tolerance and return its time.
        Returns original time_ms if no frame found within tolerance.
        """
        if self.current_data.empty:
            return time_ms

        times = self.current_data['frame_time_ms'].values
        if len(times) == 0:
            return time_ms

        # Find nearest frame using binary search
        idx = np.searchsorted(times, time_ms)

        candidates = []
        if idx > 0:
            candidates.append(times[idx - 1])
        if idx < len(times):
            candidates.append(times[idx])

        if not candidates:
            return time_ms

        # Find closest candidate
        nearest = min(candidates, key=lambda t: abs(t - time_ms))

        # Check if within tolerance
        if abs(nearest - time_ms) <= tolerance_ms:
            return nearest
        return time_ms

    def get_frame_at_time(self, time_ms: float, tolerance_ms: float = 50.0):
        """
        Per PRD 5.1: Get the frame data nearest to the given time within tolerance.
        Returns (frame_row, frame_time_ms) or (None, None) if not found.
        """
        if self.current_data.empty:
            return None, None

        times = self.current_data['frame_time_ms'].values
        idx = np.searchsorted(times, time_ms)

        candidates = []
        if idx > 0:
            candidates.append((idx - 1, times[idx - 1]))
        if idx < len(times):
            candidates.append((idx, times[idx]))

        if not candidates:
            return None, None

        # Find closest
        best_idx, best_time = min(candidates, key=lambda x: abs(x[1] - time_ms))

        if abs(best_time - time_ms) <= tolerance_ms:
            return self.current_data.iloc[best_idx], best_time
        return None, None

    def show_context_menu(self, global_pos, time_ms: float):
        """
        Per PRD 5.3: Show context menu at position with auto-snapped time.
        """
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        # Standard edit actions
        if self.timeline_type == 'edit':
            cut_action = menu.addAction("Cut")
            cut_action.triggered.connect(lambda: self._emit_cut(time_ms))

        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(lambda: self._emit_copy(time_ms))

        if self.timeline_type == 'edit':
            paste_action = menu.addAction("Paste")
            paste_action.triggered.connect(lambda: self.paste_requested.emit(time_ms, self.timeline_type))

            menu.addSeparator()

            # Insert actions
            blackout_action = menu.addAction("Insert Blackout")
            blackout_action.triggered.connect(lambda: self.insert_blackout_requested.emit(time_ms))

            color_action = menu.addAction("Insert Color Frame...")
            color_action.triggered.connect(lambda: self.insert_color_dialog_requested.emit(time_ms))

        menu.addSeparator()

        # Marker action
        marker_action = menu.addAction("Add Marker...")
        marker_action.triggered.connect(lambda: self._add_marker_at(time_ms))

        menu.exec(global_pos)

    def _emit_cut(self, time_ms: float):
        start, end = self.get_selected_region()
        if abs(end - start) > 1:
            self.cut_requested.emit(start, end, self.timeline_type)

    def _emit_copy(self, time_ms: float):
        start, end = self.get_selected_region()
        if abs(end - start) > 1:
            self.copy_requested.emit(start, end, self.timeline_type)

    def _add_marker_at(self, time_ms: float):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Marker", "Marker Name:")
        if ok and name:
            self.add_marker_requested.emit(time_ms, name)

    def is_playing(self) -> bool:
        """Check if video associated with this timeline is playing."""
        try:
            main_window = self.window()
            if self.timeline_type == 'source':
                return main_window.source_preview_widget.is_playing()
            else:
                return main_window.edit_preview_widget.is_playing()
        except:
            return False

    # --- Tool Pattern Helper Methods ---

    def zoom_at_position(self, x_pos: float, factor: float):
        """Zoom centered on x_pos. factor < 1 = zoom in, > 1 = zoom out."""
        current_range = self.plot_item.viewRange()[0]
        current_width = current_range[1] - current_range[0]
        new_width = current_width * factor

        # Apply zoom limits
        if new_width < self.min_zoom_range:
            new_width = self.min_zoom_range
        elif new_width > self.max_zoom_range:
            new_width = self.max_zoom_range

        ratio = (x_pos - current_range[0]) / current_width if current_width > 0 else 0.5
        new_start = x_pos - new_width * ratio
        new_end = new_start + new_width
        self.plot_item.setXRange(new_start, new_end, padding=0)

    def scroll_horizontal(self, delta: float):
        """Scroll horizontally by delta pixels worth of time."""
        current_range = self.plot_item.viewRange()[0]
        current_width = current_range[1] - current_range[0]
        scroll_amount = (delta / 120) * current_width * 0.1
        self.plot_item.setXRange(
            current_range[0] - scroll_amount,
            current_range[1] - scroll_amount,
            padding=0
        )

    def pan_view(self, delta_x: float):
        """Pan view by delta_x in time units."""
        # Fix flickering by setting range directly instead of translateBy
        current_range = self.plot_item.viewRange()[0]
        self.plot_item.setXRange(current_range[0] - delta_x, current_range[1] - delta_x, padding=0)

    def start_region_selection(self, time_ms: float):
        """Start a new region selection at time_ms."""
        self.region_item.setRegion([time_ms, time_ms])

    def update_region_selection(self, time_ms: float):
        """Update the end of the current region selection."""
        rgn = self.region_item.getRegion()
        self.region_item.setRegion([rgn[0], time_ms])

    def finish_region_selection(self):
        """Finalize region selection and emit signal."""
        self.on_region_changed()

    def get_region_edge_at(self, time_ms: float, tolerance_px: int = 10) -> str | None:
        """Check if time_ms is near a region edge. Returns 'region_start', 'region_end', or None."""
        start, end = self.region_item.getRegion()
        if abs(end - start) < 1:
            return None

        # Convert tolerance from pixels to time
        view_range = self.plot_item.viewRange()[0]
        view_width = view_range[1] - view_range[0]
        widget_width = self.width()
        tolerance_ms = (tolerance_px / widget_width) * view_width if widget_width > 0 else 50

        if abs(time_ms - start) <= tolerance_ms:
            return 'region_start'
        if abs(time_ms - end) <= tolerance_ms:
            return 'region_end'
        return None

    def is_in_selected_region(self, time_ms: float) -> bool:
        """Check if time_ms is within the selected region."""
        start, end = self.region_item.getRegion()
        return start <= time_ms <= end and abs(end - start) > 1

    def start_offset_drag(self, time_ms: float):
        """Start offset drag operation."""
        self.drag_start_pos = time_ms
        self.drag_offset = 0

    def update_offset_drag(self, offset: float):
        """Update offset drag with visual feedback."""
        self.drag_offset = offset
        start_ms, end_ms = self.get_selected_region()
        if (end_ms - start_ms) <= 0:
            return

        # Update ghost region
        new_start = start_ms + offset
        new_end = end_ms + offset
        self.ghost_region_item.setRegion([new_start, new_end])
        self.ghost_region_item.show()

        # Update offset label
        offset_str = f"{offset:+.2f} ms"
        new_pos_str = f"新范围: {new_start:.2f} → {new_end:.2f}"
        self.offset_label.setText(f"<b>偏移:</b> {offset_str}<br><b>目标:</b> {new_pos_str}")
        self.offset_label.adjustSize()
        self.offset_label.show()

    def finish_offset_drag(self):
        """Finish offset drag and apply if valid."""
        self.ghost_region_item.hide()
        self.offset_label.hide()
        if abs(self.drag_offset) > 0.01:
            start_ms, end_ms = self.get_selected_region()
            if abs(end_ms - start_ms) > 1:
                self.offset_requested.emit(start_ms, end_ms, self.drag_offset)
        self.drag_start_pos = None
        self.drag_offset = 0

    def resize_region_start(self, time_ms: float):
        """Resize region by moving the start edge."""
        _, end = self.region_item.getRegion()
        self.region_item.setRegion([time_ms, end])

