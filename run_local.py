from __future__ import annotations

import socket
import threading
import urllib.request
import webbrowser

import uvicorn

HOST = "127.0.0.1"
START_PORT = 5000


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
    port, already_running = choose_port()
    url = f"http://{HOST}:{port}"
    if already_running:
        print(f"Research Cultivation OS is already running: {url}")
        open_browser(url)
    else:
        print("\nResearch Cultivation OS")
        print(f"Open: {url}")
        print("Close this window or press Ctrl+C to stop the local server.")
        print("All data stays inside this project folder.\n")
        threading.Timer(1.2, open_browser, args=(url,)).start()
        uvicorn.run("app:app", host=HOST, port=port, reload=False, log_level="warning")
