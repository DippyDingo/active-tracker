"""Масштабная нормализация концептов: приводит все иконки набора
к одинаковому визуальному весу (содержимое = 64% полотна) и убирает шов
по фону, если генератор оставил свой оттенок подложки.

    python3 tools/icon_scale.py <папка>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

FILL = (11, 18, 32)     # #0b1220
RADIUS = 232
TARGET = 0.64           # доля полотна под содержимое


def content_bbox(im: Image.Image, thr: int = 26):
    small = im.resize((256, 256), Image.LANCZOS)
    px = small.load()
    xs, ys = [], []
    for y in range(20, 236):
        for x in range(20, 236):
            p = px[x, y]
            if any(abs(p[i] - FILL[i]) > thr for i in range(3)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    k = im.width / 256
    return (int(min(xs) * k), int(min(ys) * k),
            int((max(xs) + 1) * k), int((max(ys) + 1) * k))


def ring_bg(crop: Image.Image, inset: int = 2):
    px = crop.load()
    W, H = crop.size
    vals = []
    for x in range(W):
        vals.append(px[x, inset])
        vals.append(px[x, H - 1 - inset])
    for y in range(H):
        vals.append(px[inset, y])
        vals.append(px[W - 1 - inset, y])
    n = len(vals)
    return tuple(sorted(v[i] for v in vals)[n // 2] for i in range(3))


def flush_bg(crop: Image.Image):
    """Убирает шов по границе фрагмента: сдвигает ВСЁ изображение ровно на
    разницу между его фоном и подложкой приложения.

    Сдвиг равномерный, поэтому тёмные детали (силуэты листьев, тонкие линии)
    не пропадают — в отличие от по-пиксельного вытягивания фона.
    """
    bg = ring_bg(crop)
    delta = tuple(FILL[i] - bg[i] for i in range(3))
    if max(abs(d) for d in delta) <= 1:
        return crop, False
    if max(abs(d) for d in delta) > 60:
        return crop, False          # фон явно не наш — не трогаем
    px = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            p = px[x, y]
            px[x, y] = tuple(max(0, min(255, p[i] + delta[i])) for i in range(3))
    return crop, True


def process(src: Path):
    changed = 0
    for p in sorted(src.glob("v*.png")):
        im = Image.open(p).convert("RGB").resize((1024, 1024), Image.LANCZOS)
        box = content_bbox(im)
        if not box:
            continue
        crop = im.crop(box)
        crop, flushed = flush_bg(crop)
        side = int(1024 * TARGET)
        scale = side / max(crop.width, crop.height)
        nw, nh = max(1, int(crop.width * scale)), max(1, int(crop.height * scale))
        crop = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (1024, 1024), FILL)
        canvas.paste(crop, ((1024 - nw) // 2, (1024 - nh) // 2))
        canvas.save(p, optimize=True)
        changed += flushed
    print(f"{src.name}: обработано, швов исправлено: {changed}")


if __name__ == "__main__":
    process(Path(sys.argv[1]))
