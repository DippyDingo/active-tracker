"""Собирает .ico для каждого кандидата в assets/icon_candidates/ico/.

Чтобы поставить выбранный вариант в приложение, достаточно скопировать
нужный .ico поверх assets/app_icon.ico (и .png поверх assets/app_icon.png).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_icons import CAND, cut_tile, fit_square, png_bytes, render  # noqa: E402
from make_sheet import CANDIDATES  # noqa: E402
from PIL import Image  # noqa: E402
from io import BytesIO  # noqa: E402


def main() -> None:
    out_dir = CAND / "ico"
    out_dir.mkdir(exist_ok=True)
    for key, label, path in CANDIDATES:
        if not path.exists():
            print("нет файла:", path.name)
            continue
        master = fit_square(cut_tile(path), 1024)
        frames = [Image.open(BytesIO(png_bytes(master, s))) for s in (256, 128, 96, 64, 48, 40, 32, 24, 20, 16)]
        ico = out_dir / f"{key}.ico"
        frames[0].save(ico, format="ICO", sizes=[f.size for f in frames], append_images=frames[1:])
        render(master, 512).save(out_dir / f"{key}.png", optimize=True)
        print(f"{key}: {label} -> {ico.name} ({ico.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
