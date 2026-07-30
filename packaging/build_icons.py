from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "packaging" / "generated"
ICO_PATH = OUTPUT_DIR / "research-system.ico"
PNG_PATH = OUTPUT_DIR / "research-system.png"

IVORY = "#FFF9ED"
INK = "#132B47"
TERRACOTTA = "#E06445"


def point(value: tuple[float, float], size: int) -> tuple[int, int]:
    return round(value[0] * size / 108), round(value[1] * size / 108)


def render(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), IVORY)
    draw = ImageDraw.Draw(image)
    radius = max(1, round(23 * size / 108))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=IVORY)
    research_path = [
        (10, 73), (28, 73), (41, 50), (59, 50), (73, 70),
        (91, 27), (102, 27), (79, 84), (68, 84), (51, 61),
        (38, 84), (10, 84),
    ]
    cap_path = [(91, 13), (104, 13), (96, 25), (83, 25)]
    draw.polygon([point(item, size) for item in research_path], fill=INK)
    draw.polygon([point(item, size) for item in cap_path], fill=TERRACOTTA)
    return image


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base = render(512)
    base.save(PNG_PATH, optimize=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    base.save(ICO_PATH, format="ICO", sizes=[(size, size) for size in sizes])
    print(f"Generated {ICO_PATH.relative_to(ROOT)} and {PNG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
