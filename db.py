"""Stable database imports for the v3 product modules.

The schema and bootstrap live under :mod:`core`; this facade keeps the original
v3 feature modules source-compatible without carrying migration logic.
"""

from core.database import (
    DB_PATH,
    connect,
    get_setting,
    init_db,
    log_activity,
    now_iso,
    row_to_dict,
    set_setting,
    total_xp,
    transaction,
)
from core.navigation import (
    DEFAULT_NAV_LABELS,
    DEFAULT_NAV_LAYOUT,
    NAV_GROUP_DEFAULT_ITEMS,
    normalize_nav_labels,
    normalize_nav_layout,
)

__all__ = [
    "DB_PATH",
    "DEFAULT_NAV_LABELS",
    "DEFAULT_NAV_LAYOUT",
    "NAV_GROUP_DEFAULT_ITEMS",
    "connect",
    "get_setting",
    "init_db",
    "log_activity",
    "normalize_nav_labels",
    "normalize_nav_layout",
    "now_iso",
    "row_to_dict",
    "set_setting",
    "total_xp",
    "transaction",
]
