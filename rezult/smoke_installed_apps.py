"""Smoke-test grouping and ranking of discovered executable candidates."""
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.installed_apps import (
    InstalledApp,
    _deduplicate_and_rank,
    _normalized_product_name,
    _pick_game_exe,
)
from app.ui.add_dialog import _Row


def app(name: str, path: str, source: str = "start_menu", category: str = "installed"):
    return InstalledApp(name, path, path, 0, category, True, source)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "Game"), exist_ok=True)
        os.makedirs(os.path.join(root, "Base", "Binaries", "Win64Steam"), exist_ok=True)
        for path in (
            os.path.join(root, "Game", "eldenring.exe"),
            os.path.join(root, "Base", "Binaries", "Win64Steam", "CivilizationVI.exe"),
        ):
            open(path, "wb").close()
        check(os.path.normcase(_pick_game_exe(root, "ELDEN RING")) == os.path.normcase(
            os.path.join(root, "Game", "eldenring.exe")
        ), "Elden Ring nested executable is found")
        check(os.path.normcase(_pick_game_exe(root, "Sid Meier's Civilization VI")) == os.path.normcase(
            os.path.join(root, "Base", "Binaries", "Win64Steam", "CivilizationVI.exe")
        ), "Civilization VI nested executable is found")

    check(_normalized_product_name("codex-code-mode-host") == "codex", "Codex helper name normalizes")
    check(_normalized_product_name("1С Предприятие (учебная версия)") == "1с предприятие", "edition suffix normalizes")

    candidates = [
        app("Codex", r"C:\Apps\Codex\app\ChatGPT.exe", "registry"),
        app("codex", r"C:\Apps\Codex\app\resources\codex.exe"),
        app("codex-code-mode-host", r"C:\Apps\Codex\app\resources\codex-code-mode-host.exe"),
        app("Microsoft Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "registry"),
        app("Microsoft Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\157.0\msedge.exe"),
        app("Overwolf", r"C:\Program Files (x86)\Overwolf\Overwolf.exe", "registry"),
        app("OverwolfBrowser", r"C:\Program Files (x86)\Overwolf\0.311.1.6\OverwolfBrowser.exe"),
        app("1С Предприятие (учебная версия)", r"C:\Program Files (x86)\1cv8\common\1cestart.exe", "registry"),
        app("1С Предприятие (толстый клиент)", r"C:\Program Files (x86)\1c\8.3.27\bin\1cv8.exe"),
        app("1С Предприятие (тонкий клиент)", r"C:\Program Files (x86)\1c\8.3.27\bin\1cv8c.exe"),
        app("Python", r"C:\Users\lex\Documents\active-tracker\.venv\Scripts\python.exe", "running"),
        app("Python 3.13 (64-bit)", r"C:\Users\lex\AppData\Local\Python\python.exe", "registry"),
    ]
    ranked = _deduplicate_and_rank(candidates)
    primary = [item for item in ranked if item.primary]
    check(sum(item.name == "Codex" for item in primary) == 1, "Codex has one primary")
    check(sum(item.name == "Microsoft Edge" for item in primary) == 1, "Edge versions collapse")
    check(sum(item.name == "Overwolf" for item in primary) == 1, "Overwolf browser collapses")
    check(sum(item.name == "1С Предприятие (учебная версия)" for item in primary) == 1, "1C variants collapse")
    check(any(item.name == "codex-code-mode-host" and not item.primary for item in ranked), "Codex helper remains secondary")
    check(sum(item.name.startswith("Python") and item.primary for item in ranked) == 1, "Python entries collapse")
    check(sum(item.primary for item in ranked) < len(ranked), "all mode has secondary candidates")

    # Keep the UI predicate aligned with the data contract: installed is the
    # primary catalog, all includes secondary candidates, system is explicit.
    primary_item = next(item for item in ranked if item.primary)
    secondary_item = next(item for item in ranked if not item.primary and item.category != "system")
    system_item = InstalledApp("Windows component", r"C:\\Windows\\system32\\x.exe", "", 0, "system", False)
    check(_Row.category_matches(SimpleNamespace(app=primary_item), "installed", False), "installed shows primary")
    check(not _Row.category_matches(SimpleNamespace(app=secondary_item), "installed", False), "installed hides secondary")
    check(_Row.category_matches(SimpleNamespace(app=secondary_item), "all", False), "all shows secondary")
    check(not _Row.category_matches(SimpleNamespace(app=system_item), "all", False), "system stays hidden")
    check(_Row.category_matches(SimpleNamespace(app=system_item), "all", True), "system toggle shows system")
    print("OK: installed app grouping smoke checks passed")


if __name__ == "__main__":
    main()
