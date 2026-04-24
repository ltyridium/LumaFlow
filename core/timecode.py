from __future__ import annotations


def format_time_ms(total_ms: int | float | None) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    if total_ms is None:
        value = 0
    else:
        value = max(0, int(total_ms))

    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def parse_timecode(value: str) -> int:
    """
    Parse a timecode string into milliseconds.

    Supported formats:
    - HH:MM:SS.mmm
    - MM:SS.mmm
    - bare milliseconds, e.g. 12345

    The fractional part is optional for colon-separated formats and accepts
    one to three digits. Components larger than 59 are allowed and are
    normalized by total-millisecond arithmetic.
    """
    text = str(value).strip()
    if not text:
        raise ValueError("Timecode is empty.")

    if text.isdigit():
        return int(text)

    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError("Unsupported timecode format.")

    if len(parts) == 3:
        hours_text, minutes_text, seconds_text = parts
    else:
        hours_text = "0"
        minutes_text, seconds_text = parts

    hours = _parse_integer_component(hours_text, "hours")
    minutes = _parse_integer_component(minutes_text, "minutes")
    seconds, milliseconds = _parse_seconds_component(seconds_text)

    return ((hours * 60 + minutes) * 60 + seconds) * 1_000 + milliseconds


def _parse_integer_component(text: str, name: str) -> int:
    if not text.isdigit():
        raise ValueError(f"Invalid {name} component.")
    return int(text)


def _parse_seconds_component(text: str) -> tuple[int, int]:
    if "." in text:
        seconds_text, milliseconds_text = text.split(".", 1)
        if not milliseconds_text or not milliseconds_text.isdigit() or len(milliseconds_text) > 3:
            raise ValueError("Invalid milliseconds component.")
        milliseconds = int(milliseconds_text.ljust(3, "0"))
    else:
        seconds_text = text
        milliseconds = 0

    if not seconds_text.isdigit():
        raise ValueError("Invalid seconds component.")

    return int(seconds_text), milliseconds
