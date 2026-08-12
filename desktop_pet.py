"""A lightweight, resizable and animated desktop research companion."""
from __future__ import annotations

import base64
import json
import math
import random
import tempfile
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from runtime_paths import USER_CONFIG_DIR


PET_LINES = (
    "先喝一口水，再继续读这一段。",
    "把这张图讲成一句因果关系，便是进展。",
    "卡住时，只写下：作者究竟证明了什么？",
    "休息 30 秒，回来只推进一个最小动作。",
    "不要替论文补结论，先找它的证据。",
)
SETTINGS_PATH = USER_CONFIG_DIR / "desktop_pet.json"


def _asset_path() -> Path:
    bundled = Path(__file__).resolve().parent / "static" / "pet" / "lingzhi_assistant.png"
    if bundled.exists():
        return bundled
    encoded = bundled.with_suffix(".png.b64")
    target = Path(tempfile.gettempdir()) / "wendao-lingzhi-assistant.png"
    if encoded.exists() and not target.exists():
        target.write_bytes(base64.b64decode(encoded.read_text(encoding="ascii")))
    return target


def _load_size() -> int:
    try:
        return max(110, min(480, int(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("size", 220))))
    except (OSError, ValueError, json.JSONDecodeError):
        return 220


def _save_size(size: int) -> None:
    try:
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps({"size": size}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def run_pet() -> None:
    root = tk.Tk()
    root.title("灵知")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    transparent = "#ff00ff"
    try:
        root.wm_attributes("-transparentcolor", transparent)
    except tk.TclError:
        transparent = "#f4e7d5"
    root.configure(bg=transparent)

    original = Image.open(_asset_path()).convert("RGBA")
    desired_size = _load_size()
    phase = 0.0
    dragging = False
    start_x = start_y = 0
    image_label = tk.Label(root, bg=transparent, borderwidth=0, cursor="hand2")
    image_label.pack()
    hint = tk.Label(
        root, text="灵知 · 点击互动｜滚轮调大小｜右键菜单", bg="#213242", fg="#fff4d2",
        font=("Microsoft YaHei UI", 9), padx=8, pady=4,
    )
    menu = tk.Menu(root, tearoff=False)

    def render(*, animate: bool = True) -> None:
        nonlocal phase
        wobble = 1.0 + (0.025 * math.sin(phase) if animate and not dragging else 0)
        width = max(90, round(desired_size * wobble))
        height = max(90, round(original.height * width / max(original.width, 1)))
        frame = original.resize((width, height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(frame)
        image_label.configure(image=photo)
        image_label.image = photo

    def animate() -> None:
        nonlocal phase
        phase += 0.22
        render()
        root.after(130, animate)

    def show_hint(_event=None) -> None:
        hint.configure(text=f"灵知 · {random.choice(PET_LINES)}")
        hint.place(x=4, y=max(0, image_label.winfo_height() - 6), anchor="sw")
        root.after(4200, hint.place_forget)

    def resize(delta: int) -> None:
        nonlocal desired_size
        desired_size = max(110, min(480, desired_size + delta))
        _save_size(desired_size)
        render(animate=False)
        hint.configure(text=f"灵知 · 当前大小 {desired_size}px")
        hint.place(x=4, y=max(0, image_label.winfo_height() - 6), anchor="sw")
        root.after(1600, hint.place_forget)

    def wheel(event) -> None:
        resize(16 if event.delta > 0 else -16)

    def drag_start(event) -> None:
        nonlocal dragging, start_x, start_y
        dragging = True
        start_x, start_y = event.x, event.y

    def drag_move(event) -> None:
        root.geometry(f"+{root.winfo_x() + event.x - start_x}+{root.winfo_y() + event.y - start_y}")

    def drag_end(_event) -> None:
        nonlocal dragging
        dragging = False

    def popup(event) -> None:
        menu.tk_popup(event.x_root, event.y_root)

    menu.add_command(label="放大", command=lambda: resize(30))
    menu.add_command(label="缩小", command=lambda: resize(-30))
    menu.add_command(label="恢复默认大小", command=lambda: resize(220 - desired_size))
    menu.add_separator()
    menu.add_command(label="关闭灵知", command=root.destroy)
    image_label.bind("<Button-1>", show_hint)
    image_label.bind("<ButtonPress-1>", drag_start, add="+")
    image_label.bind("<B1-Motion>", drag_move)
    image_label.bind("<ButtonRelease-1>", drag_end)
    image_label.bind("<MouseWheel>", wheel)
    image_label.bind("<Button-4>", lambda _event: resize(16))
    image_label.bind("<Button-5>", lambda _event: resize(-16))
    image_label.bind("<Button-3>", popup)
    root.bind("<Escape>", lambda _event: root.destroy())
    root.geometry("+1040+620")
    render(animate=False)
    animate()
    root.mainloop()
