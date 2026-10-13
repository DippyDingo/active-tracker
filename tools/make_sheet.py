"""Превью-лист всех кандидатов иконки Nodexy (тёмная + светлая тема, крупно и мелко)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_icons import ASSETS, CAND, cut_tile, fit_square, render  # noqa: E402

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

PAD = 34
BIG = 200
COL = 252
ROW = 340
SMALLS = (64, 32, 16)


def build_sheet(names: list[tuple[str, str, Path]], out: Path) -> None:
    f_title = ImageFont.truetype(FONT_B, 30)
    f_name = ImageFont.truetype(FONT_B, 16)
    f_lab = ImageFont.truetype(FONT_R, 13)

    cols = 5
    rows = (len(names) + cols - 1) // cols
    width = PAD * 2 + cols * COL
    height = PAD + 50 + rows * ROW + 26
    img = Image.new("RGB", (width, height), (18, 22, 31))
    d = ImageDraw.Draw(img)
    d.text((PAD, 16), "Nodexy — варианты иконки", font=f_title, fill=(228, 233, 242))

    for i, (_key, name, path) in enumerate(names):
        master = fit_square(cut_tile(path), 1024)
        cx = PAD + (i % cols) * COL
        cy = PAD + 56 + (i // cols) * ROW
        d.text((cx, cy), f"{i + 1:02d}. {name}", font=f_name, fill=(150, 168, 198))
        big = render(master, BIG)
        img.paste(big, (cx + (COL - BIG) // 2, cy + 22), big)
        # мелкие размеры — под крупной иконкой, «как в системе»
        total = sum(SMALLS) + 14 * (len(SMALLS) - 1)
        sx = cx + (COL - total) // 2
        for s in SMALLS:
            small = render(master, s)
            img.paste(small, (sx, cy + 22 + BIG + 16 + (64 - s) // 2), small)
            d.text((sx + s // 2 - 6, cy + 22 + BIG + 78), f"{s}", font=f_lab, fill=(120, 136, 162))
            sx += s + 14

    img.save(out)
    print("sheet:", out, img.size)


def main() -> None:
    batch = sys.argv[1] if len(sys.argv) > 1 else ""
    names = [n for n in CANDIDATES if n[0].startswith(batch)]
    build_sheet(names, CAND / f"preview_{batch or 'all'}.png")


CANDIDATES: list[tuple[str, str, Path]] = [
    ("v01", "Сегментное кольцо", CAND / "v01_segments.png"),
    ("v02", "Неоновые песочные часы", CAND / "v02_hourglass_neon.png"),
    ("v03", "Клавиша с циферблатом", CAND / "v03_keycap.png"),
    ("v04", "Столбцы-график", CAND / "v04_bars.png"),
    ("v05", "Граф узлов", CAND / "v05_nodes.png"),
    ("v06", "Спидометр", CAND / "v06_gauge.png"),
    ("v07", "Яркая заливка", CAND / "v07_solid_bright.png"),
    ("v08", "Изометрия (куб-часы)", CAND / "v08_isometric.png"),
    ("v09", "Светлая плитка", CAND / "v09_light_tile.png"),
    ("v10", "Радар", CAND / "v10_radar.png"),
]


if __name__ == "__main__":
    main()
