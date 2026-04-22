from __future__ import annotations

import sys
from pathlib import Path


def runtime_base_path() -> Path:
    """Return the base directory that contains bundled runtime resources."""
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolve a file path inside the bundled ``resources`` directory."""
    return runtime_base_path().joinpath("resources", *parts)


def icon_path() -> Path:
    """Resolve the main application icon path."""
    return resource_path("icons", "icon.png")
