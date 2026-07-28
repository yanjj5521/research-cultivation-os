from __future__ import annotations

from runtime_paths import APP_ROOT


def _read_version() -> str:
    version_file = APP_ROOT / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return "2.1.1"


APP_VERSION = _read_version()
