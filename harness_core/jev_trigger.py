"""Cheap automatic-observer policy; manual preview/observe are unaffected."""
from __future__ import annotations

from typing import Any


def should_observe(config: dict[str, Any], payload: dict[str, Any]) -> bool:
    settings = config.get("jev_observer", {})
    if not isinstance(settings, dict):
        return False
    if (
        settings.get("enabled") is not True
        or settings.get("allow_remote_state") is not True
        or settings.get("mode", "shadow") != "shadow"
    ):
        return False
    trigger = settings.get("automatic_trigger", "failures")
    if trigger == "always":
        return type(payload.get("passed")) is bool
    if trigger == "failures":
        return payload.get("passed") is False
    # manual, malformed and unknown policies never silently spend API budget.
    return False
