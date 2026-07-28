from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

HOST = "127.0.0.1"
START_PORT = 5000


def preconfigure_runtime() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--portable", action="store_true", help="Keep data beside the executable.")
    parser.add_argument("--data-dir", default="", help="Use an explicit data directory.")
    parser.add_argument("--open-data", action="store_true", help="Open the active data directory.")
    parser.add_argument("--migrate-from", default="", help="Import data from a v2.0 source folder.")
    parser.add_argument("--self-check", action="store_true", help="Initialize the app and exit.")
    args = parser.parse_args()
    if args.portable:
        executable_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        os.environ["RESEARCH_OS_PORTABLE"] = "1"
        os.environ["RESEARCH_OS_DATA_DIR"] = str(executable_root / "user_data")
    elif args.data_dir:
        os.environ["RESEARCH_OS_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    return args


def is_research_os(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/stats", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def choose_port() -> tuple[int, bool]:
    for port in range(START_PORT, START_PORT + 20):
        if is_research_os(port):
            return port, True
        if port_available(port):
            return port, False
    raise RuntimeError("No free local port was found between 5000 and 5019.")


def open_browser(url: str) -> None:
    webbrowser.open_new(url)


if __name__ == "__main__":
    args = preconfigure_runtime()
    from runtime_paths import DATA_ROOT, ensure_data_layout, migrate_adjacent_legacy_data, migrate_legacy_data

    ensure_data_layout()
    if args.migrate_from:
        source = Path(args.migrate_from)
        if not migrate_legacy_data(source):
            raise SystemExit("The selected folder has no v2.0 database or storage directory.")
        print(f"Data migrated from: {source.resolve()}")
        print(f"Data directory: {DATA_ROOT}")
        raise SystemExit(0)
    migrate_adjacent_legacy_data()
    if args.open_data:
        try:
            os.startfile(DATA_ROOT)  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(DATA_ROOT.as_uri())
        raise SystemExit(0)

    from app import app as web_app
    if args.self_check:
        from fastapi.testclient import TestClient
        from version import APP_VERSION

        with TestClient(web_app) as client:
            for path in ("/", "/workspaces", "/settings", "/api/stats"):
                response = client.get(path)
                if response.status_code != 200:
                    raise SystemExit(
                        f"Packaged self-check failed: {path} returned HTTP {response.status_code}."
                    )
            if "gate-dual-search" not in client.get("/").text:
                raise SystemExit("Packaged self-check failed: the homepage template is incomplete.")
        print(f"Research Cultivation OS {APP_VERSION} self-check PASS")
        print(f"Data: {DATA_ROOT}")
        raise SystemExit(0)

    port, already_running = choose_port()
    url = f"http://{HOST}:{port}"
    if already_running:
        print(f"Research Cultivation OS is already running: {url}")
        open_browser(url)
    else:
        print("\nResearch Cultivation OS")
        print(f"Open: {url}")
        print(f"Data: {DATA_ROOT}")
        print("Close this window or press Ctrl+C to stop the local server.\n")
        threading.Timer(1.2, open_browser, args=(url,)).start()
        uvicorn.run(web_app, host=HOST, port=port, reload=False, log_level="warning")
