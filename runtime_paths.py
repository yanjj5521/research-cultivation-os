from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


PRODUCT_DIR_NAME = "ResearchCultivationOS"
USER_STORAGE_NAMES = (
    "uploads",
    "simulations",
    "research_foundation",
    "deliveries",
    "note_images",
    "profile",
    "sync_exports",
    "hub_backups",
    "hub_releases",
    "autobackups",
    "backups",
)
INSTANCE_NAMES = (
    "research_os.db",
    "hub.db",
    "hub_secret.txt",
    "HUB_ADMIN_CREDENTIALS.txt",
)


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", "")
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parent


def _distribution_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_user_data_root() -> Path:
    explicit = os.environ.get("RESEARCH_OS_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if (
        os.environ.get("RESEARCH_OS_PORTABLE", "").strip() == "1"
        or (_distribution_root() / "portable.flag").is_file()
    ):
        return _distribution_root() / "user_data"
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data).expanduser().resolve() / PRODUCT_DIR_NAME
        return Path.home() / "AppData" / "Local" / PRODUCT_DIR_NAME
    # Source/development mode remains fully backward compatible.
    return _resource_root()


APP_ROOT = _resource_root()
DISTRIBUTION_ROOT = _distribution_root()
DATA_ROOT = _default_user_data_root()
INSTANCE_DIR = DATA_ROOT / "instance"
STORAGE_ROOT = DATA_ROOT / "storage"
USER_CONFIG_DIR = DATA_ROOT / "user_config"


def ensure_data_layout() -> None:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for name in USER_STORAGE_NAMES:
        (STORAGE_ROOT / name).mkdir(parents=True, exist_ok=True)


def _sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()


def _copy_tree(source: Path, target: Path, *, overwrite: bool) -> bool:
    """Copy regular files without replacing an existing user's file by default."""

    changed = False
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_symlink():
            continue
        destination = target / path.relative_to(source)
        if path.is_dir():
            if not destination.exists():
                destination.mkdir(parents=True, exist_ok=True)
                changed = True
            continue
        if not path.is_file() or (destination.exists() and not overwrite):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        changed = True
    return changed


def migrate_legacy_data(source_root: Path, *, overwrite: bool = False) -> bool:
    """Move legacy user data into the separated runtime data directory safely."""

    source_root = source_root.expanduser().resolve()
    if source_root == DATA_ROOT:
        return False
    source_db = source_root / "instance" / "research_os.db"
    target_db = INSTANCE_DIR / "research_os.db"
    source_storage = source_root / "storage"
    source_config = source_root / "user_config"
    if not source_db.exists() and not source_storage.exists() and not source_config.exists():
        return False
    ensure_data_layout()
    changed = False
    if source_db.exists() and (overwrite or not target_db.exists()):
        _sqlite_backup(source_db, target_db)
        changed = True
    for name in INSTANCE_NAMES[1:]:
        source = source_root / "instance" / name
        target = INSTANCE_DIR / name
        if source.exists() and (overwrite or not target.exists()):
            shutil.copy2(source, target)
            changed = True
    for name in USER_STORAGE_NAMES:
        source = source_storage / name
        target = STORAGE_ROOT / name
        if source.exists():
            changed = _copy_tree(source, target, overwrite=overwrite) or changed
    if source_config.exists():
        changed = _copy_tree(
            source_config,
            USER_CONFIG_DIR,
            overwrite=overwrite,
        ) or changed
    if changed:
        marker = USER_CONFIG_DIR / "MIGRATED_FROM.txt"
        if overwrite or not marker.exists():
            marker.write_text(f"Migrated from: {source_root}\n", encoding="utf-8")
    return changed


def migrate_adjacent_legacy_data() -> bool:
    """Adopt data placed beside a packaged app by the v2.0 safe updater."""

    if DATA_ROOT == DISTRIBUTION_ROOT:
        return False
    if (INSTANCE_DIR / "research_os.db").exists():
        return False
    return migrate_legacy_data(DISTRIBUTION_ROOT)


ensure_data_layout()
