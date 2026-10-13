"""Превью иконок Nodexy: тёмная/светлая тема, реальные размеры в px и увеличение x4."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_icons import ASSETS, CAND, cut_tile, fit_square, render  # noqa: E402

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

CANDIDATES = [("A. N-монограмма", CAND / "A_monogram.png"), ("C. Пульс", CAND / "C_pulse.png")]
THEMES = [("Тёмная тема", (11, 18, 32)), ("Светлая тема", (236, 239, 246))]
SIZES = [64, 48, 32, 16]
ZOOM = [32, 16]

PAD = 34
BIG = 240
CELL = 74
ZOOM_CELL = {32: 150, 16: 96}


def build_sheet(out: Path) -> None:
    f_title = ImageFont.truetype(FONT_B, 31)
    f_theme = ImageFont.truetype(FONT_B, 23)
    f_name = ImageFont.truetype(FONT_B, 18)
    f_lab = ImageFont.truetype(FONT_R, 14)

    masters = {name: fit_square(cut_tile(path), 1024) for name, path in CANDIDATES}

    row_h = 44 + BIG + 30
    panel_h = 46 + len(CANDIDATES) * row_h + 14
    width = PAD + BIG + 24 + len(SIZES) * CELL + sum(ZOOM_CELL.values()) + 140 + PAD
    height = PAD + 50 + len(THEMES) * (panel_h + PAD) + 30
    img = Image.new("RGB", (width, height), (18, 22, 31))
    d = ImageDraw.Draw(img)
    d.text((PAD, 16), "Nodexy — финальные варианты иконки", font=f_title, fill=(228, 233, 242))

    y = PAD + 50
    for theme_name, bg in THEMES:
        light = sum(bg) > 400
        fg, fg_dim = ((38, 48, 68), (108, 122, 146)) if light else ((224, 231, 242), (132, 148, 176))
        d.rectangle([PAD - 14, y, width - PAD + 14, y + panel_h], fill=bg)
        d.text((PAD, y + 12), theme_name, font=f_theme, fill=fg)

        for i, (name, _) in enumerate(CANDIDATES):
            ry = y + 46 + i * row_h
            d.text((PAD, ry), name, font=f_name, fill=fg_dim)

            big = render(masters[name], BIG)
            img.paste(big, (PAD, ry + 30), big)
            d.text((PAD, ry + 30 + BIG + 4), "256 px", font=f_lab, fill=fg_dim)

            x = PAD + BIG + 24
            for s in SIZES:
                small = render(masters[name], s)
                img.paste(small, (x, ry + 30 + (BIG - s) // 2), small)
                d.text((x, ry + 30 + BIG + 4), f"{s}", font=f_lab, fill=fg_dim)
                x += CELL

            for s in ZOOM:
                z = render(masters[name], s).resize((s * 4, s * 4), Image.NEAREST)
                cell = ZOOM_CELL[s]
                img.paste(z, (x + (cell - s * 4) // 2, ry + 30 + (BIG - s * 4) // 2), z)
                d.text((x, ry + 30 + BIG + 4), f"{s} px (x4)", font=f_lab, fill=fg_dim)
                x += cell + 18

        y += panel_h + PAD

    img.save(out)
    print("preview:", out, img.size)


if __name__ == "__main__":
    build_sheet(ASSETS / "icon_candidates" / "preview.png")
