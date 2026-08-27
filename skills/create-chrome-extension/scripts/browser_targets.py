"""Shared browser-target rules for Addonry extension tooling."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

TARGET_CHOICES = ("chrome", "firefox", "both")
SUPPORTED_BROWSERS = ("chrome", "firefox")
FIREFOX_GUID_RE = re.compile(
    r"^\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}$"
)
FIREFOX_EMAIL_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$")


def browsers_for_choice(choice: str) -> tuple[str, ...]:
    """Expand CLI target choice into stable browser order."""
    normalized = choice.strip().lower()
    if normalized not in TARGET_CHOICES:
        raise ValueError(f"browser target must be one of: {', '.join(TARGET_CHOICES)}")
    return SUPPORTED_BROWSERS if normalized == "both" else (normalized,)


def validate_firefox_id(value: str) -> str:
    """Validate Firefox extension ID accepted by Gecko signing metadata."""
    candidate = value.strip()
    if FIREFOX_GUID_RE.fullmatch(candidate) or FIREFOX_EMAIL_ID_RE.fullmatch(candidate):
        return candidate
    raise ValueError("Firefox ID must be a GUID in braces or an email-style extension ID")


def project_browsers(root: Path, explicit: str = "auto") -> tuple[str, ...]:
    """Resolve requested browsers from CLI override or project metadata."""
    if explicit != "auto":
        return browsers_for_choice(explicit)
    metadata_path = root / ".addonry" / "project.json"
    if metadata_path.is_file():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            browsers = payload.get("browsers")
            if (
                isinstance(browsers, list)
                and browsers
                and all(isinstance(item, str) and item in SUPPORTED_BROWSERS for item in browsers)
            ):
                return tuple(browser for browser in SUPPORTED_BROWSERS if browser in browsers)
    return ("chrome",)


def manifest_for_browser(manifest: dict[str, Any], browser: str) -> dict[str, Any]:
    """Create browser-specific manifest without mutating shared source manifest."""
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(f"unsupported browser: {browser}")
    result = copy.deepcopy(manifest)
    background = result.get("background")
    if isinstance(background, dict):
        if browser == "chrome":
            background.pop("scripts", None)
            background.pop("preferred_environment", None)
        else:
            background.pop("service_worker", None)
        if not background:
            result.pop("background", None)
    if browser == "chrome":
        result.pop("browser_specific_settings", None)
    else:
        result.pop("minimum_chrome_version", None)
        result.pop("key", None)
    return result
