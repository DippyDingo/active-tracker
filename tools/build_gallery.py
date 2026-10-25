"""Сборка данных для сайта-галереи иконок.

Сканирует assets/icon-concepts/icons/ и пишет manifest.js (window.ICON_DATA),
который читает index.html. Работает и по http, и при открытии файла напрямую.

Использование:
    python3 tools/build_gallery.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets" / "icon-concepts"
ICONS = ROOT / "icons"

SETS = [
    {
        "letter": "A",
        "title": "Набор A — флэт-минимализм",
        "desc": "Чистые формы, холодные тона. Лучше всех читается в трее и в списке приложений.",
        "names": [
            ("A01", "Классика"),
            ("A02", "Срез"),
            ("A03", "Грядка"),
            ("A04", "В кольце"),
            ("A05", "Половинки"),
            ("A06", "Трио"),
            ("A07", "Вектор"),
            ("A08", "Инверсия"),
            ("A09", "Геометрия"),
            ("A10", "Пиксели"),
        ],
        "notes": {"A08": "фон под плиткой не тёмный — проверь в трее"},
    },
    {
        "letter": "B",
        "title": "Набор B — дуотон-силуэт",
        "desc": "Градиенты пинк→виолет, плоские силуэты. Самые яркие в панели задач.",
        "names": [
            ("B01", "Градиент"),
            ("B02", "Инверсия"),
            ("B03", "Часы"),
            ("B04", "Двойной"),
            ("B05", "Профиль"),
            ("B06", "Неон"),
            ("B07", "Ризо"),
            ("B08", "Шов"),
            ("B09", "Стикер"),
            ("B10", "В листе"),
            ("B11", "По фото"),
        ],
        "notes": {"B11": "восстановлена по фото пользователя из утерянной первой подборки"},
    },
    {
        "letter": "C",
        "title": "Набор C — эмблема-знак",
        "desc": "Геометрический лого-знак: минимум элементов, максимум узнаваемости.",
        "names": [
            ("C01", "Базовая"),
            ("C02", "Только циан"),
            ("C03", "Только белый"),
            ("C04", "Инверсия"),
            ("C05", "Двойное кольцо"),
            ("C06", "Капсула"),
            ("C07", "Треугольник"),
            ("C08", "Ромб"),
            ("C09", "Гексагон"),
            ("C10", "Монограмма R"),
        ],
        "notes": {},
    },
]


def build() -> dict:
    data = {"sets": [], "stats": {}}
    total = 0
    for meta in SETS:
        icons = []
        for key, name in meta["names"]:
            f512 = ICONS / f"{key}-512.png"
            if not f512.exists():
                continue
            icons.append({
                "id": key,
                "name": name,
                "src": f"icons/{key}-512.png",
                "small": f"icons/{key}-256.png" if (ICONS / f"{key}-256.png").exists() else f"icons/{key}-512.png",
                "big": f"icons/{key}-1024.png" if (ICONS / f"{key}-1024.png").exists() else None,
                "note": meta["notes"].get(key),
            })
        total += len(icons)
        data["sets"].append({
            "letter": meta["letter"],
            "title": meta["title"],
            "desc": meta["desc"],
            "opacity": 1.0,
            "ready": len(icons) == 10,
            "icons": icons,
        })
    data["stats"] = {"total": total, "sets": len(data["sets"])}
    return data


def main():
    data = build()
    payload = "window.ICON_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
    (ROOT / "manifest.js").write_text(payload, encoding="utf-8")
    (ROOT / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("готово:", ROOT / "manifest.js", "иконок:", data["stats"]["total"])


if __name__ == "__main__":
    main()
