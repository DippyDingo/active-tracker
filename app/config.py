import json
import os
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "ActiveTracker"


def app_dir() -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def config_path() -> Path:
    return APP_DIR / "config.json"


def default_db_path() -> Path:
    return APP_DIR / "tracker.db"


def read_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(data: dict) -> None:
    try:
        app_dir()
        config_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def get_db_path() -> str:
    return str(read_config().get("db_path", "") or "")


def set_db_path(path: str) -> None:
    cfg = read_config()
    cfg["db_path"] = str(path)
    write_config(cfg)


def log_error(message: str) -> None:
    try:
        import traceback
        from datetime import datetime

        with open(APP_DIR / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now().isoformat()} {message} ===\n")
            f.write(traceback.format_exc())
    except Exception:
        pass
