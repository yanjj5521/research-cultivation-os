from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

from runtime_paths import DATA_ROOT, INSTANCE_DIR, STORAGE_ROOT, USER_CONFIG_DIR

BASE = DATA_ROOT
DB = INSTANCE_DIR / "research_os.db"
STORAGE = STORAGE_ROOT


def main() -> None:
    root = Tk(); root.withdraw(); root.attributes("-topmost", True)
    selected = filedialog.askopenfilename(title="Select a Research OS data backup ZIP", filetypes=[("ZIP backup", "*.zip")])
    if not selected:
        return
    backup = Path(selected)
    safety = BASE / "storage" / "backups" / f"before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    safety.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        shutil.copy2(DB, safety / DB.name)
    if STORAGE.exists():
        shutil.copytree(STORAGE / "uploads", safety / "uploads", dirs_exist_ok=True) if (STORAGE / "uploads").exists() else None
        shutil.copytree(STORAGE / "simulations", safety / "simulations", dirs_exist_ok=True) if (STORAGE / "simulations").exists() else None
        shutil.copytree(STORAGE / "research_foundation", safety / "research_foundation", dirs_exist_ok=True) if (STORAGE / "research_foundation").exists() else None
        shutil.copytree(STORAGE / "deliveries", safety / "deliveries", dirs_exist_ok=True) if (STORAGE / "deliveries").exists() else None
        shutil.copytree(STORAGE / "note_images", safety / "note_images", dirs_exist_ok=True) if (STORAGE / "note_images").exists() else None
        shutil.copytree(STORAGE / "profile", safety / "profile", dirs_exist_ok=True) if (STORAGE / "profile").exists() else None
    if USER_CONFIG_DIR.exists():
        shutil.copytree(
            USER_CONFIG_DIR,
            safety / "user_config",
            dirs_exist_ok=True,
        )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with zipfile.ZipFile(backup) as zf:
                root = target.resolve()
                for member in zf.infolist():
                    destination = (target / member.filename).resolve()
                    if destination != root and root not in destination.parents:
                        raise RuntimeError("Unsafe path found in the backup archive.")
                    zf.extract(member, target)
            db_candidates = list(target.rglob("research_os.db"))
            if not db_candidates:
                raise RuntimeError("No research_os.db was found in this backup.")
            with sqlite3.connect(db_candidates[0]) as conn:
                conn.execute("PRAGMA integrity_check").fetchone()
            DB.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_candidates[0], DB)
            storage_candidates = [p for p in target.rglob("storage") if p.is_dir()]
            if storage_candidates:
                source_storage = storage_candidates[0]
                for name in ("uploads", "simulations", "research_foundation", "deliveries", "note_images", "profile"):
                    source = source_storage / name
                    if source.exists():
                        shutil.copytree(source, STORAGE / name, dirs_exist_ok=True)
            else:
                uploads = next((p for p in target.rglob("uploads") if p.is_dir()), None)
                if uploads:
                    shutil.copytree(uploads, STORAGE / "uploads", dirs_exist_ok=True)
            config_source = next(
                (p for p in target.rglob("user_config") if p.is_dir()),
                None,
            )
            if config_source:
                shutil.copytree(
                    config_source,
                    USER_CONFIG_DIR,
                    dirs_exist_ok=True,
                )
        messagebox.showinfo("Restore complete", "Data restored. Start Research Cultivation OS again.")
    except Exception as exc:
        messagebox.showerror("Restore failed", str(exc))


if __name__ == "__main__":
    main()
