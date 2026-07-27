from __future__ import annotations

import socket
import threading
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from hub_db import HUB_ADMIN_PATH, init_hub_db

HOST = "0.0.0.0"
LOCAL_HOST = "127.0.0.1"
PORT = 5050


def is_running() -> bool:
    try:
        with urllib.request.urlopen(f"http://{LOCAL_HOST}:{PORT}/health", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def port_available() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, PORT))
            return True
        except OSError:
            return False


def open_browser() -> None:
    webbrowser.open_new(f"http://{LOCAL_HOST}:{PORT}")


if __name__ == "__main__":
    init_hub_db()
    if is_running():
        print(f"Shared Hub is already running: http://{LOCAL_HOST}:{PORT}")
        open_browser()
    elif not port_available():
        print(f"Port {PORT} is occupied by another program.")
        input("Press Enter to close...")
    else:
        print("\nResearch Cultivation OS Shared Hub v2.0.2")
        print(f"Local admin page: http://{LOCAL_HOST}:{PORT}")
        print("LAN address: http://<this-computer-LAN-IP>:5050")
        print("For Internet access, use Tailscale Funnel, a named Cloudflare Tunnel, or a small VPS.")
        if HUB_ADMIN_PATH.exists():
            print(f"First-run admin credentials: {HUB_ADMIN_PATH}")
        print("Keep this window open. Press Ctrl+C to stop.\n")
        threading.Timer(1.0, open_browser).start()
        uvicorn.run("hub_app:app", host=HOST, port=PORT, reload=False, log_level="info", proxy_headers=True, forwarded_allow_ips="127.0.0.1")
