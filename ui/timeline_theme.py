from __future__ import annotations


DEFAULT_VISUAL_THEME = "dark_theme"

_REQUIRED_THEME_FIELDS = {
    "timeline_background",
    "audio_background",
    "grid",
    "grid_alpha",
    "axis_text",
    "axis_line",
    "zoom_text",
    "offset_background_rgba",
    "offset_text",
    "selection_fill_rgba",
    "ghost_fill_rgba",
    "playback_head",
    "playback_head_hover",
    "idx_playback",
    "idx_region_rgba",
    "idx_frame",
    "frame_separator",
    "function_line",
}


THEME_PROFILES: dict[str, dict[str, object]] = {
    "dark_theme": {
        "timeline_background": "#2A2A2A",
        "audio_background": "#202020",
        "grid": "#555555",
        "grid_alpha": 0.20,
        "axis_text": "#DCDCDC",
        "axis_line": "#555555",
        "zoom_text": "#F3F3F3",
        "offset_background_rgba": "rgba(18, 18, 18, 210)",
        "offset_text": "#F5F5F5",
        "selection_fill_rgba": (90, 150, 255, 60),
        "ghost_fill_rgba": (140, 185, 255, 90),
        "playback_head": "#FF5A5A",
        "playback_head_hover": "#FF8A8A",
        "idx_playback": "#FF5A5A",
        "idx_region_rgba": (90, 150, 255, 180),
        "idx_frame": "#B8B8B8",
        "frame_separator": "#111111",
        "function_line": "#303030",
    },
    "light_theme": {
        "timeline_background": "#FFFFFF",
        "audio_background": "#F7F7F7",
        "grid": "#C5C5C5",
        "grid_alpha": 0.24,
        "axis_text": "#333333",
        "axis_line": "#C5C5C5",
        "zoom_text": "#2A2A2A",
        "offset_background_rgba": "rgba(255, 255, 255, 230)",
        "offset_text": "#333333",
        "selection_fill_rgba": (70, 120, 220, 55),
        "ghost_fill_rgba": (120, 160, 245, 85),
        "playback_head": "#D63B3B",
        "playback_head_hover": "#F05C5C",
        "idx_playback": "#D63B3B",
        "idx_region_rgba": (70, 120, 220, 180),
        "idx_frame": "#6B6B6B",
        "frame_separator": "#202020",
        "function_line": "#555555",
    },
}


def get_visual_theme_profile(theme_name: str | None) -> dict[str, object]:
    profile = THEME_PROFILES.get(theme_name or "", THEME_PROFILES[DEFAULT_VISUAL_THEME])
    missing_fields = _REQUIRED_THEME_FIELDS.difference(profile.keys())
    if missing_fields:
        raise ValueError(
            f"Theme '{theme_name}' is missing fields: {sorted(missing_fields)}"
        )
    return dict(profile)
