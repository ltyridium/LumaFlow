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
def hsv_to_rgb(h, s, v):
    """Convert HSV (0-1) to RGB (0-1)"""
    if s == 0.0:
        return v, v, v

    h = h * 6.0
    i = int(h)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))

    i = i % 6
    if i == 0: return v, t, p
    if i == 1: return q, v, p
    if i == 2: return p, v, t
    if i == 3: return p, q, v
    if i == 4: return t, p, v
    return v, p, q

@jit(nopython=True, cache=True)
def rgb_to_hsv(r, g, b):
    """Convert RGB (0-1) to HSV (0-1)"""
    max_val = max(r, max(g, b))
    min_val = min(r, min(g, b))
    diff = max_val - min_val

    if diff == 0.0:
        h = 0.0
    elif max_val == r:
        h = ((g - b) / diff) % 6.0
    elif max_val == g:
        h = ((b - r) / diff) + 2.0
    else:
        h = ((r - g) / diff) + 4.0

    h = h / 6.0
    s = 0.0 if max_val == 0.0 else diff / max_val
    v = max_val

    return h, s, v

# Non-JIT wrappers for UI layer
def hsv_to_rgb_4bit(h, s, v):
    """Convert HSV (0-1) to 4-bit RGB (0-15)"""
    r, g, b = hsv_to_rgb(h, s, v)
    return int(r * 15 + 0.5), int(g * 15 + 0.5), int(b * 15 + 0.5)

def rgb_4bit_to_hsv(r, g, b):
    """Convert 4-bit RGB (0-15) to HSV (0-1)"""
    return rgb_to_hsv(r / 15.0, g / 15.0, b / 15.0)

@jit(nopython=True, cache=True)
def compute_gradient_colors(times, positions, hues, saturations, values, num_channels, mode):
    """
    Gradient color computation with three modes:
    mode = 0: RGB blending
    mode = 1: HSV clockwise
    mode = 2: HSV counter-clockwise
    """
    n_times = len(times)
    n_points = len(positions)
    colors = np.zeros((n_times, num_channels, 3))

    for t_idx in prange(n_times):
        progress = times[t_idx] / times[-1] if times[-1] > 0 else 0

        # Find segment
        seg_idx = 0
        for i in range(n_points - 1):
            if progress >= positions[i] and progress <= positions[i + 1]:
                seg_idx = i
                break

        # Interpolate within segment
        p0, p1 = positions[seg_idx], positions[seg_idx + 1]
        t = (progress - p0) / (p1 - p0) if p1 > p0 else 0

        if mode == 0:
            # RGB blending mode
            r0, g0, b0 = hsv_to_rgb(hues[seg_idx], saturations[seg_idx], values[seg_idx])
            r1, g1, b1 = hsv_to_rgb(hues[seg_idx + 1], saturations[seg_idx + 1], values[seg_idx + 1])
            r = r0 + t * (r1 - r0)
            g = g0 + t * (g1 - g0)
            b = b0 + t * (b1 - b0)
        else:
            # HSV interpolation modes
            h0, s0, v0 = hues[seg_idx], saturations[seg_idx], values[seg_idx]
            h1, s1, v1 = hues[seg_idx + 1], saturations[seg_idx + 1], values[seg_idx + 1]

            # Interpolate hue based on mode
            if mode == 1:
                # Clockwise
                if h1 < h0:
                    h1 += 1.0
                h = h0 + t * (h1 - h0)
                h = h % 1.0
            else:
                # Counter-clockwise
                if h1 > h0:
                    h1 -= 1.0
                h = h0 + t * (h1 - h0)
                if h < 0:
                    h += 1.0

            # Linear interpolation for saturation and value
            s = s0 + t * (s1 - s0)
            v = v0 + t * (v1 - v0)

            r, g, b = hsv_to_rgb(h, s, v)

        for ch in range(num_channels):
            colors[t_idx, ch, 0] = int(r * 15 + 0.5)
            colors[t_idx, ch, 1] = int(g * 15 + 0.5)
            colors[t_idx, ch, 2] = int(b * 15 + 0.5)

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
