"""Нормализация сгенерированных иконок-концептов.

Приводит картинку к единому виду: квадрат 1024x1024, скруглённые углы,
подложка цвета фона приложения (#0b1220). Убирает внешние поля генератора
(белые/серые рамки) и зачищает кромки.

Использование:
    python3 tools/icon_normalize.py <папка> "<подпись1|подпись2|...>" "<заголовок>"
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FILL = (11, 18, 32)      # #0b1220 — фон приложения
RADIUS = 232             # скругление углов в 1024px
TOL = 45                 # допуск совпадения с цветом внешнего фона


def bg_bbox(orig: Image.Image, work: int = 256) -> tuple[int, int, int, int] | None:
    """Границы иконки: заливка от краёв по цвету углов (белый, серый и т.п.)."""
    small = orig.resize((work, work), Image.LANCZOS)
    k = orig.width / work
    px = small.load()
    cs = [px[1, 1], px[work - 2, 1], px[1, work - 2], px[work - 2, work - 2]]
    bg = tuple(sum(c[i] for c in cs) // 4 for i in range(3))

    def same(p):
        return all(abs(p[i] - bg[i]) <= TOL for i in range(3))

    vis = [[False] * work for _ in range(work)]
    dq = deque()
    for x in range(work):
        for y in (0, work - 1):
            if same(px[x, y]) and not vis[y][x]:
                vis[y][x] = True
                dq.append((x, y))
    for y in range(work):
        for x in (0, work - 1):
            if same(px[x, y]) and not vis[y][x]:
                vis[y][x] = True
                dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < work and 0 <= ny < work and not vis[ny][nx] and same(px[nx, ny]):
                vis[ny][nx] = True
                dq.append((nx, ny))

    pts = [(x, y) for y in range(work) for x in range(work) if not vis[y][x]]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (int(min(xs) * k), int(min(ys) * k),
            int((max(xs) + 1) * k), int((max(ys) + 1) * k))


def edge_clean(icon: Image.Image, band: int = 26) -> Image.Image:
    """Растворяет остатки внешнего фона по кромке в цвет подложки."""
    W, H = icon.size
    px = icon.load()
    for y in range(H):
        for x in range(W):
            d = min(x, y, W - 1 - x, H - 1 - y)
            if d >= band:
                continue
            t = d / band
            c = px[x, y]
            px[x, y] = tuple(round(FILL[i] * (1 - t) + c[i] * t) for i in range(3))
    return icon


def normalize(path: Path, out: Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    cropped = False
    box = bg_bbox(im)
    if box:
        w, h = im.size
        if box != (0, 0, w, h):
            mx = int((box[2] - box[0]) * 0.02)
            my = int((box[3] - box[1]) * 0.02)
            box = (max(0, box[0] - mx), max(0, box[1] - my),
                   min(w, box[2] + mx), min(h, box[3] + my))
            im = im.crop(box)
            cropped = True
    s = max(im.size)
    sq = Image.new("RGB", (s, s), FILL)
    sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    icon = sq.resize((1024, 1024), Image.LANCZOS)
    if cropped:
        icon = edge_clean(icon)
    mask = Image.new("L", (1024, 1024), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 1023, 1023], radius=RADIUS, fill=255)
    base = Image.new("RGB", (1024, 1024), FILL)
    base.paste(icon, (0, 0), mask)
    base.save(out)
    return base


def sheet(files, labels, out, title, cols=5, tray=True):
    CELL, PAD, CAP = 320, 22, 56
    rows = (len(files) + cols - 1) // cols
    W = PAD + cols * (CELL + PAD)
    TRAY = 96 if tray else 0
    H = PAD + 56 + rows * (CELL + CAP) + TRAY
    im_sheet = Image.new("RGB", (W, H), "#0b1220")
    d = ImageDraw.Draw(im_sheet)
    f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    f_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    f_lab = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    d.text((PAD, PAD), title, font=f_title, fill="#22d3ee")
    y0 = PAD + 56
    for i, (f, lab) in enumerate(zip(files, labels)):
        r, c = divmod(i, cols)
        x = PAD + c * (CELL + PAD)
        y = y0 + r * (CELL + CAP)
        pic = Image.open(f).convert("RGB").resize((CELL, CELL), Image.LANCZOS)
        im_sheet.paste(pic, (x, y))
        d.rectangle([x - 1, y - 1, x + CELL, y + CELL], outline="#24344d", width=1)
        d.text((x + 4, y + CELL + 8), f"{i + 1:02d}", font=f_num, fill="#22d3ee")
        d.text((x + 44, y + CELL + 10), lab, font=f_lab, fill="#9ca3af")
    if tray:
        f_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        yb = y0 + rows * (CELL + CAP) + 16
        d.text((PAD, yb), "как читаются маленькими (48 / 32 px):", font=f_small, fill="#6b7280")
        xx = PAD
        for f in files:
            pic = Image.open(f).convert("RGB")
            for s_px in (48, 32):
                im_sheet.paste(pic.resize((s_px, s_px), Image.LANCZOS),
                               (xx, yb + 26 + (48 - s_px)))
                xx += s_px + 12
            xx += 26
    im_sheet.save(out)
    return im_sheet


def run(src: Path, labels: list[str], title: str):
    dst = src / "final"
    dst.mkdir(exist_ok=True)
    files = sorted(p for p in src.glob("v*.png"))
    finals = []
    for p in files:
        f = dst / f"{p.stem}-1024.png"
        normalize(p, f)
        finals.append(f)
    sh = sheet(finals, labels, src / "00-sheet.png", title)
    print("normalized:", len(finals), "sheet:", sh.size)


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2].split("|"), sys.argv[3] if len(sys.argv) > 3 else "")
