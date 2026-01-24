import numpy as np
from numba import jit, prange

@jit(nopython=True, cache=True)
def compute_breathing_brightness(times, min_bright, max_bright):
    """使用Numba JIT优化的呼吸效果亮度计算"""
    brightness = np.zeros(len(times))
    for i in prange(len(times)):
        # 归一化时间到 [0, 2π] 范围
        normalized_time = (times[i] / times[-1]) * 2 * np.pi if len(times) > 1 else 0
        sine_val = (np.sin(normalized_time) + 1) / 2  # 0 to 1 sine wave
        brightness[i] = min_bright + sine_val * (max_bright - min_bright)
    return brightness

@jit(nopython=True, cache=True)
def compute_rainbow_colors(times, speed, num_channels):
    """使用Numba JIT优化的彩虹颜色计算"""
    n_times = len(times)
    colors = np.zeros((n_times, num_channels, 3))  # RGB for each channel and time
    
    for t_idx in prange(n_times):
        base_hue = (times[t_idx] / 1000.0 * speed) % 1.0
        
        for ch in range(num_channels):
            channel_hue = (base_hue + ch / num_channels) % 1.0
            
            # HSV to RGB conversion (optimized for Numba)
            h = channel_hue * 6.0
            c = 1.0  # Chroma (saturation = 1.0, value = 1.0)
            x = c * (1.0 - abs((h % 2.0) - 1.0))
            
            if h < 1.0:
                r, g, b = c, x, 0.0
            elif h < 2.0:
                r, g, b = x, c, 0.0
            elif h < 3.0:
                r, g, b = 0.0, c, x
            elif h < 4.0:
                r, g, b = 0.0, x, c
            elif h < 5.0:
                r, g, b = x, 0.0, c
            else:
                r, g, b = c, 0.0, x
            
            # Scale to 0-15 range
            colors[t_idx, ch, 0] = int(r * 15)
            colors[t_idx, ch, 1] = int(g * 15)
            colors[t_idx, ch, 2] = int(b * 15)
    
    return colors

@jit(nopython=True, cache=True)
def compute_channel_colors(brightness_array, base_color_r, base_color_g, base_color_b):
    """使用Numba JIT优化的通道颜色计算"""
    n_frames = len(brightness_array)
    colors = np.zeros((n_frames, 3), dtype=np.int32)
    
    for i in prange(n_frames):
        colors[i, 0] = int(base_color_r * brightness_array[i])
        colors[i, 1] = int(base_color_g * brightness_array[i])
        colors[i, 2] = int(base_color_b * brightness_array[i])
    
    return colors

@jit(nopython=True, cache=True)
def create_scatter_data_optimized(times, colors_array, num_channels):
    """使用Numba优化的散点图数据生成"""
    n_frames = len(times)
    n_points = n_frames * num_channels
    
    # 预分配数组
    pos_x = np.zeros(n_points)
    pos_y = np.zeros(n_points)
    colors_r = np.zeros(n_points, dtype=np.int32)
    colors_g = np.zeros(n_points, dtype=np.int32)
    colors_b = np.zeros(n_points, dtype=np.int32)
    
    idx = 0
    for frame_idx in prange(n_frames):
        time_ms = times[frame_idx]
        for ch in range(num_channels):
            pos_x[idx] = time_ms
            pos_y[idx] = ch
            colors_r[idx] = int(colors_array[frame_idx, ch, 0] * 17)  # 0-15 to 0-255
            colors_g[idx] = int(colors_array[frame_idx, ch, 1] * 17)
            colors_b[idx] = int(colors_array[frame_idx, ch, 2] * 17)
            idx += 1
    
    return pos_x, pos_y, colors_r, colors_g, colors_b
