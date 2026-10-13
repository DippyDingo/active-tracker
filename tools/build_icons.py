"""Сборка .ico/.png для Nodexy из исходных картинок-кандидатов.

Что делает:
1. вырезает плитку иконки из картинки генератора: фон определяется по углам,
   вырезается заливкой от края (не задевает шум внутри плитки), край смягчается;
2. «заматовывает» прозрачный фон под цвет плитки — чтобы при уменьшении
   не появлялась светлая кайма от серого/белого фона генератора;
3. собирает мультиразмерный .ico (16..256) и 512x512 png с прозрачностью;
4. мелкие размеры (16..40) делает из «усиленного» варианта — чтобы читались в трее.

Запуск:  python tools/build_icons.py
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
CAND = ROOT / "assets" / "icon_candidates"
ASSETS = ROOT / "assets"

ICO_SIZES = [256, 128, 96, 64, 48, 40, 32, 24, 20, 16]
SMALL = {16, 20, 24, 32, 40, 48}  # размеры, где берём усиленный вариант
BG_TOLERANCE = 46  # минимальное отличие пикселя от фона, чтобы счесть его плиткой


def _corner_bg(im: Image.Image) -> tuple[int, int, int]:
    w, h = im.size
    k = max(4, w // 64)
    patches = [(0, 0), (w - k, 0), (0, h - k), (w - k, h - k)]
    px = [im.getpixel((x + i, y + j)) for x, y in patches for i in range(k) for j in range(k)]
    return tuple(sorted(p[c] for p in px)[len(px) // 2] for c in range(3))  # type: ignore[return-value]


def _alpha_mask(im: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    acc = Image.new("L", im.size, 0)
    for ch, base in zip(im.split(), bg):
        acc = ImageChops.lighter(acc, ch.point(lambda v, base=base: min(255, abs(v - base) * 4)))
    cand = acc.point(lambda v: 255 if v > BG_TOLERANCE else 0)

    # фон — только то, что связано с краем изображения (шум внутри плитки не трогаем)
    flood = cand.copy()
    w, h = flood.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (0, h // 2), (w - 1, h // 2), (w // 2, h - 1)):
        if flood.getpixel(seed) == 0:
            ImageDraw.floodfill(flood, seed, 128, thresh=8)
    fg = flood.point(lambda v: 0 if v == 128 else 255)
    # закрываем щели внутри плитки, затем мягкий край
    fg = fg.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    return fg.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: min(255, int(v * 1.45)))


def _unmatte(im: Image.Image) -> Image.Image:
    """Подменяет прозрачный фон средним цветом плитки, чтобы не было каймы при ресайзе."""
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    solid = a.point(lambda v: 255 if v > 220 else 0)
    mean = tuple(round(c) for c in ImageStat.Stat(rgb, mask=solid).mean) if solid.getbbox() else (0, 0, 0)
    mean_img = Image.new("RGB", im.size, mean)
    return Image.merge("RGBA", (*Image.composite(rgb, mean_img, a).split(), a))


def cut_tile(src: Path) -> Image.Image:
    im = Image.open(src).convert("RGB")
    alpha = _alpha_mask(im, _corner_bg(im))
    tile = Image.merge("RGBA", (*im.split(), alpha))
    box = alpha.getbbox() or (0, 0, *im.size)
    return _unmatte(tile.crop(box))


def _thicken(base: Image.Image, size: int) -> Image.Image:
    """Утолщает светлые штрихи (кольцо, букву), чтобы иконка не рассыпалась на 16-48 px."""
    r, g, b, a = base.split()
    lum = base.convert("L")
    mask = lum.point(lambda v: 255 if v > 55 else 0)
    passes = max(0, round(0.45 * base.width / size) - 1)
    for _ in range(passes):
        mask = mask.filter(ImageFilter.MaxFilter(3))
    mask = ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(0.9)), a)

    bright = ImageEnhance.Brightness(base).enhance(1.32)
    bright = ImageEnhance.Color(bright).enhance(1.18)
    br, bg_, bb, _ = bright.split()
    out = Image.merge(
        "RGBA",
        (
            Image.composite(br, r, mask),
            Image.composite(bg_, g, mask),
            Image.composite(bb, b, mask),
            a,
        ),
    )
    return ImageEnhance.Sharpness(out).enhance(1.3)


def fit_square(im: Image.Image, size: int, pad_ratio: float = 0.035) -> Image.Image:
    """Вписывает плитку в квадрат с небольшим отступом, как у системных иконок."""
    pad = int(size * pad_ratio)
    inner = size - 2 * pad
    w, h = im.size
    scale = inner / max(w, h)
    rs = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(rs, ((size - rs.width) // 2, (size - rs.height) // 2), rs)
    return canvas


def render(master: Image.Image, size: int) -> Image.Image:
    if size not in SMALL:
        return fit_square(master, size)
    out = _thicken(fit_square(master, 256), size)
    if size != 256:
        out = out.resize((size, size), Image.LANCZOS)
    return out


def png_bytes(master: Image.Image, size: int) -> bytes:
    buf = BytesIO()
    render(master, size).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build(src: Path, ico: Path, png: Path) -> Image.Image:
    master = fit_square(cut_tile(src), 1024)
    render(master, 512).save(png, optimize=True)
    frames = [Image.open(BytesIO(png_bytes(master, s))) for s in ICO_SIZES]
    frames[0].save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=frames[1:])
    print(f"{src.name} -> {ico.name} ({ico.stat().st_size // 1024} КБ), {png.name} 512x512")
    return master


# Какая из идей сейчас стоит в приложении (assets/app_icon.*) и как называются .ico вариантов
SOURCES = {"A": ("A_monogram.png", "app_icon"), "C": ("C_pulse.png", "app_icon")}
DEFAULT = "A"


def main() -> None:
    for key, (src, base) in SOURCES.items():
        suffix = "" if key == DEFAULT else f"_{key.lower()}"
        build(CAND / src, ASSETS / f"{base}{suffix}.ico", ASSETS / f"{base}{suffix}.png")


if __name__ == "__main__":
    main()
