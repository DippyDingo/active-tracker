"""Пайплайн иконок-концептов: сырая генерация -> готовые PNG для сайта и приложения.

Шаги:
  1) обрезка внешних полей генератора (белые/серые рамки);
  2) выравнивание фона фрагмента к подложке приложения равномерным сдвигом
     (тёмные детали при этом не теряются);
  3) масштабная нормализация: содержимое = 66% полотна, у всех иконок
     одинаковый визуальный вес;
  4) скруглённые углы и подложка #0b1220;
  5) выгрузка: icons/<id>-1024.png (для сборки), -512.png и -256.png (для сайта).

Использование:
    python3 tools/icon_pipeline.py <id1> <id2> ...      # или без аргументов: все raw/*
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

FILL = (11, 18, 32)      # #0b1220 — фон темы «Полночь»
RADIUS = 232             # скругление в 1024px
TARGET = 0.66            # доля полотна под содержимое
TOL = 45                 # допуск цвета внешнего фона
ROOT = Path(__file__).resolve().parents[1] / "assets" / "icon-concepts"


def outer_bbox(im: Image.Image, work: int = 256):
    """Границы содержимого: заливка от краёв по цвету углов."""
    small = im.resize((work, work), Image.LANCZOS)
    k = im.width / work
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


def content_bbox(im: Image.Image, thr: int = 26):
    """Границы содержимого внутри плитки (по отличию от подложки)."""
    small = im.resize((256, 256), Image.LANCZOS)
    px = small.load()
    xs, ys = [], []
    for y in range(18, 238):
        for x in range(18, 238):
            p = px[x, y]
            if any(abs(p[i] - FILL[i]) > thr for i in range(3)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    k = im.width / 256
    return (int(min(xs) * k), int(min(ys) * k),
            int((max(xs) + 1) * k), int((max(ys) + 1) * k))


def ring_bg(im: Image.Image):
    """Фон плитки: медиана по четырём площадкам в серединах сторон
    (внутри плитки, минуя белый холст и скруглённые углы)."""
    px = im.load()
    W, H = im.size
    d = max(3, int(W * 0.06))
    s = max(2, int(W * 0.02))
    vals = []
    for cx, cy in ((W // 2, d), (W // 2, H - 1 - d), (d, H // 2), (W - 1 - d, H // 2)):
        for y in range(max(0, cy - s), min(H, cy + s + 1)):
            for x in range(max(0, cx - s), min(W, cx + s + 1)):
                vals.append(px[x, y])
    n = len(vals)
    return tuple(sorted(v[i] for v in vals)[n // 2] for i in range(3))


def scrub_canvas(im: Image.Image, bright: int = 150):
    """Убирает белый холст генератора: светлые пиксели, связанные с углами,
    заменяет подложкой. Белый холст окружает скруглённую плитку снаружи и
    иначе оставляет белые «точки» в углах готовой иконки."""
    px = im.load()
    W, H = im.size
    seen = set()
    for cx, cy in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
        if min(px[cx, cy][:3]) <= bright:
            continue
        dq = [(cx, cy)]
        seen.add((cx, cy))
        while dq:
            x, y = dq.pop()
            px[x, y] = FILL
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in seen \
                        and min(px[nx, ny][:3]) > bright:
                    seen.add((nx, ny))
                    dq.append((nx, ny))
    return im


def flush_bg(im: Image.Image):
    """Сдвигает картинку целиком так, чтобы её фон совпал с подложкой."""
    bg = ring_bg(im)
    delta = tuple(FILL[i] - bg[i] for i in range(3))
    if max(abs(d) for d in delta) <= 1 or max(abs(d) for d in delta) > 60:
        return im
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            p = px[x, y]
            px[x, y] = tuple(max(0, min(255, p[i] + delta[i])) for i in range(3))
    return im


def process(src: Path, out_dir: Path, raw_dir: Path):
    im = Image.open(src).convert("RGB")
    box = outer_bbox(im)
    if box and box != (0, 0, *im.size):
        mx = int((box[2] - box[0]) * 0.02)
        my = int((box[3] - box[1]) * 0.02)
        im = im.crop((max(0, box[0] - mx), max(0, box[1] - my),
                      min(im.width, box[2] + mx), min(im.height, box[3] + my)))
    im = im.resize((1024, 1024), Image.LANCZOS)
    im = scrub_canvas(im)
    im = flush_bg(im)

    cb = content_bbox(im)
    if cb:
        content = im.crop(cb)
        side = int(1024 * TARGET)
        scale = side / max(content.width, content.height)
        nw, nh = max(1, int(content.width * scale)), max(1, int(content.height * scale))
        content = content.resize((nw, nh), Image.LANCZOS)
        base = Image.new("RGB", (1024, 1024), FILL)
        base.paste(content, ((1024 - nw) // 2, (1024 - nh) // 2))
        im = base

    mask = Image.new("L", (1024, 1024), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 1023, 1023], radius=RADIUS, fill=255)
    tile = Image.new("RGB", (1024, 1024), FILL)
    tile.paste(im, (0, 0), mask)

    out_dir.mkdir(parents=True, exist_ok=True)
    tile.save(out_dir / f"{src.stem}-1024.png", optimize=True)          # для сборки
    tile.resize((512, 512), Image.LANCZOS).save(out_dir / f"{src.stem}-512.png", optimize=True)
    tile.resize((256, 256), Image.LANCZOS).save(out_dir / f"{src.stem}-256.png", optimize=True)
    return True


def main():
    raw = ROOT / "raw"
    out = ROOT / "icons"
    ids = sys.argv[1:] or sorted(p.stem for p in raw.glob("*.png"))
    done = 0
    for i in ids:
        src = raw / f"{i}.png"
        if not src.exists():
            print("нет:", src)
            continue
        process(src, out, raw)
        done += 1
    print("обработано:", done, "->", out)


if __name__ == "__main__":
    main()
