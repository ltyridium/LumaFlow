from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSettings
from core.resource_paths import resource_path


APP_ORG = "LumaFlow"
APP_NAME = "LumaFlow"
LANGUAGE_SETTING_KEY = "ui/language"
DEFAULT_LANGUAGE = "zh-CN"
SUPPORTED_LANGUAGES = ("zh-CN", "en-US")
RESOURCE_DIR = resource_path("i18n")


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def normalize_language(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LANGUAGE

    normalized = str(language_code).strip().replace("_", "-")
    lowered = normalized.lower()
    mapping = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "en": "en-US",
        "en-us": "en-US",
    }
    return mapping.get(lowered, DEFAULT_LANGUAGE)


def get_settings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def get_language() -> str:
    settings = get_settings()
    return normalize_language(settings.value(LANGUAGE_SETTING_KEY, DEFAULT_LANGUAGE, str))


def set_language(language_code: str) -> str:
    normalized = normalize_language(language_code)
    settings = get_settings()
    settings.setValue(LANGUAGE_SETTING_KEY, normalized)
    return normalized


@lru_cache(maxsize=None)
def _load_messages(language_code: str) -> dict[str, str]:
    language = normalize_language(language_code)
    path = RESOURCE_DIR / f"{language}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def get_messages(language_code: str | None = None) -> dict[str, str]:
    language = normalize_language(language_code or get_language())
    messages = dict(_load_messages(DEFAULT_LANGUAGE))
    messages.update(_load_messages(language))
    return messages


def tr(key: str, default: str | None = None, language: str | None = None, **kwargs) -> str:
    messages = get_messages(language)
    text = messages.get(key, default if default is not None else key)
    if kwargs:
        try:
            return text.format_map(_SafeFormatDict(kwargs))
        except Exception:
            return text
    return text


def get_supported_languages() -> tuple[str, ...]:
    return SUPPORTED_LANGUAGES


def clear_message_cache() -> None:
    _load_messages.cache_clear()
