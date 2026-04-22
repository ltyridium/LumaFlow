from __future__ import annotations


def clamp_visible_range(
    start_ms: float,
    end_ms: float,
    max_time_ms: float | None,
) -> tuple[float, float]:
    """Clamp a visible X range to ``[0, max_time_ms]`` while preserving width."""
    start = float(start_ms)
    end = float(end_ms)
    if end < start:
        start, end = end, start

    width = max(0.0, end - start)

    if max_time_ms is None or max_time_ms <= 0:
        if start < 0:
            return 0.0, width
        return start, end

    max_time = max(0.0, float(max_time_ms))

    if width >= max_time:
        return 0.0, max_time

    if start < 0:
        start = 0.0
        end = width

    if end > max_time:
        end = max_time
        start = max(0.0, end - width)

    return start, end
