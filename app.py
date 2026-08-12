"""Compatibility entry point for runners and frozen builds."""

from web.app import app
from web.runtime import (
    PROFILE_DIR,
    current_realm,
    navigation_labels,
    navigation_layout,
)

__all__ = [
    "PROFILE_DIR",
    "app",
    "current_realm",
    "navigation_labels",
    "navigation_layout",
]
