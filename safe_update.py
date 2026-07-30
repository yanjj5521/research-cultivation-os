from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
USER_STORAGE_NAMES = (
    "uploads", "simulations", "research_foundation", "deliveries", "note_images", "profile", "sync_exports",
    "hub_backups", "hub_releases",
)
INSTANCE_NAMES = (
    "research_os.db", "hub.db", "hub_secret.txt", "HUB_ADMIN_CREDENTIALS.txt",
)


def choose_zip() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        value = filedialog.askopenfilename(title="选择科研系统新版 ZIP", filetypes=[("ZIP版本包", "*.zip")])
        root.destroy()
        return Path(value).resolve() if value else None
    except Exception:
        raw = input("Paste the release ZIP path: ").strip().strip('"')
        return Path(raw).resolve() if raw else None


def safe_members(zf: zipfile.ZipFile):
    for info in zf.infolist():
        path = Path(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe path in ZIP: {info.filename}")
        yield info


def sqlite_backup(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()


def make_recovery_backup() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BASE_DIR / "storage" / "update_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="research_os_update_"))
    try:
        instance = stage / "instance"; instance.mkdir()
        sqlite_backup(BASE_DIR / "instance" / "research_os.db", instance / "research_os.db")
        sqlite_backup(BASE_DIR / "instance" / "hub.db", instance / "hub.db")
        for name in ("hub_secret.txt", "HUB_ADMIN_CREDENTIALS.txt"):
            source = BASE_DIR / "instance" / name
            if source.exists(): shutil.copy2(source, instance / name)
        storage = stage / "storage"; storage.mkdir()
        for name in USER_STORAGE_NAMES:
            source = BASE_DIR / "storage" / name
            if source.exists(): shutil.copytree(source, storage / name, dirs_exist_ok=True)
        (stage / "manifest.json").write_text(json.dumps({"created_at": datetime.now().astimezone().isoformat(), "source": str(BASE_DIR)}, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = shutil.make_archive(str(backup_dir / f"before_update_{stamp}"), "zip", root_dir=stage)
        return Path(archive)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def discover_root(extracted: Path) -> Path:
    children = [p for p in extracted.iterdir() if p.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        candidate = children[0]
        if (candidate / "app.py").exists() or (candidate / "ResearchCultivationOS" / "app.py").exists():
            if (candidate / "ResearchCultivationOS" / "app.py").exists():
                return candidate / "ResearchCultivationOS"
            return candidate
    if (extracted / "ResearchCultivationOS" / "app.py").exists():
        return extracted / "ResearchCultivationOS"
    if (extracted / "app.py").exists():
        return extracted
    for path in extracted.rglob("app.py"):
        if path.parent.name == "ResearchCultivationOS" or (path.parent / "db.py").exists():
            return path.parent
    raise ValueError("ZIP 中没有找到科研系统程序根目录。")


def target_name(root: Path) -> str:
    version_file = root / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else datetime.now().strftime("%Y%m%d")
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in version)
    return f"ResearchCultivationOS_{safe}"


def migrate_data(target: Path) -> None:
    (target / "instance").mkdir(parents=True, exist_ok=True)
    sqlite_backup(BASE_DIR / "instance" / "research_os.db", target / "instance" / "research_os.db")
    sqlite_backup(BASE_DIR / "instance" / "hub.db", target / "instance" / "hub.db")
    for name in ("hub_secret.txt", "HUB_ADMIN_CREDENTIALS.txt"):
        source = BASE_DIR / "instance" / name
        if source.exists(): shutil.copy2(source, target / "instance" / name)
    for name in USER_STORAGE_NAMES:
        source = BASE_DIR / "storage" / name
        if source.exists(): shutil.copytree(source, target / "storage" / name, dirs_exist_ok=True)
    (target / "MIGRATED_FROM.txt").write_text(f"Migrated from: {BASE_DIR}\nAt: {datetime.now().astimezone().isoformat()}\n", encoding="utf-8")


def main() -> None:
    release = choose_zip()
    if not release:
        print("No release selected."); return
    if not release.exists() or release.suffix.lower() != ".zip":
        raise SystemExit("Selected file is not a valid ZIP.")
    print("[1/4] Creating a recovery backup...")
    recovery = make_recovery_backup()
    print(f"Backup: {recovery}")
    temp = Path(tempfile.mkdtemp(prefix="research_os_release_"))
    try:
        print("[2/4] Validating and extracting release...")
        with zipfile.ZipFile(release) as zf:
            list(safe_members(zf))
            zf.extractall(temp)
        source_root = discover_root(temp)
        target = BASE_DIR.parent / target_name(source_root)
        index = 2
        while target.exists():
            target = BASE_DIR.parent / f"{target_name(source_root)}_{index}"; index += 1
        print(f"[3/4] Installing new version to: {target}")
        shutil.copytree(source_root, target, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "research_os.db*", "hub.db*", "HUB_ADMIN_CREDENTIALS.txt", "hub_secret.txt"))
        print("[4/4] Migrating personal data and collaboration settings...")
        migrate_data(target)
        print("\nSAFE UPDATE COMPLETED")
        print(f"New version: {target}")
        print("Double-click Start_Research_OS.cmd in the new folder.")
        print("Keep the old folder until the new version has been verified.")
        try: os.startfile(target)  # type: ignore[attr-defined]
        except Exception: pass
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    main()
