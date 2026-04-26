from __future__ import annotations

from core.timeline_bounds import clamp_visible_range


DEFAULT_RENDER_OVERSCAN_RATIO = 0.5


def expand_render_range(
    view_range: tuple[float, float],
    limit_ms: float | None,
    overscan_ratio: float = DEFAULT_RENDER_OVERSCAN_RATIO,
) -> tuple[float, float]:
    start_ms, end_ms = view_range
    width_ms = end_ms - start_ms
    if width_ms <= 0:
        return start_ms, end_ms

    overscan_ms = width_ms * overscan_ratio
    return clamp_visible_range(start_ms - overscan_ms, end_ms + overscan_ms, limit_ms)


def is_view_range_within_buffer(
    view_range: tuple[float, float],
    buffered_range: tuple[float, float] | None,
) -> bool:
    if buffered_range is None:
        return False
    return (
        view_range[0] >= buffered_range[0]
        and view_range[1] <= buffered_range[1]
    )


def scaled_render_width_pixels(
    view_range: tuple[float, float],
    render_range: tuple[float, float],
    viewport_width_pixels: float,
) -> int:
    viewport_width_ms = max(view_range[1] - view_range[0], 1.0)
    render_width_ms = max(render_range[1] - render_range[0], viewport_width_ms)
    scale = render_width_ms / viewport_width_ms
    return max(int(viewport_width_pixels * scale), int(viewport_width_pixels))


def is_stale_render_result(result_generation: int, latest_generation: int) -> bool:
    return result_generation < latest_generation


def build_render_cache_key(
    render_range: tuple[float, float],
    render_width_pixels: int,
    viewport_width_pixels: float,
    device_pixel_ratio: float = 1.0,
) -> tuple[float, int, int, float]:
    render_span_ms = max(float(render_range[1]) - float(render_range[0]), 1.0)
    return (
        round(render_span_ms, 3),
        int(render_width_pixels),
        int(max(viewport_width_pixels, 1.0)),
        round(float(device_pixel_ratio), 3),
    )


def is_render_cache_compatible(
    view_range: tuple[float, float],
    buffered_range: tuple[float, float] | None,
    buffered_cache_key: tuple[float, int, int, float] | None,
    request_cache_key: tuple[float, int, int, float] | None,
) -> bool:
    if not is_view_range_within_buffer(view_range, buffered_range):
        return False
    if buffered_cache_key is None or request_cache_key is None:
        return False
    return buffered_cache_key == request_cache_key
