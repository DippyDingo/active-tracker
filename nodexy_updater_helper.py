"""Hidden Windows updater helper for REDIS.

This process is intentionally separate from the main application. It waits for
one exact PID, runs the downloaded Inno Setup installer without a shell, then
starts the updated executable. No console or visible window is created.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def log(path: Path, message: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")
    except OSError:
        pass


def pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def target_running(exe: Path) -> bool:
    try:
        import psutil
        wanted = str(exe.resolve()).casefold()
        for process in psutil.process_iter(["pid", "exe"]):
            try:
                if process.info["exe"] and str(Path(process.info["exe"]).resolve()).casefold() == wanted:
                    return True
            except (OSError, psutil.Error):
                continue
    except Exception:
        return False
    return False


def run(args: argparse.Namespace) -> int:
    log_path = Path(args.log)
    lock_path = Path(args.lock)
    setup = Path(args.setup)
    restart = Path(args.restart)
    target_dir = Path(args.dir).resolve()
    # Helper нельзя обновлять, пока он запущен из каталога приложения. Перед
    # основной работой перенесём выполнение во временную копию.
    if getattr(sys, "frozen", False) and os.environ.get("NODEXY_HELPER_TEMP") != "1":
        temp_copy = Path(tempfile.gettempdir()) / f"REDISUpdater-{os.getpid()}.exe"
        try:
            shutil.copy2(Path(sys.executable), temp_copy)
            child_env = os.environ.copy()
            child_env["NODEXY_HELPER_TEMP"] = "1"
            subprocess.Popen(
                [str(temp_copy), *sys.argv[1:]],
                cwd=str(temp_copy.parent),
                env=child_env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return 0
        except Exception as exc:
            log(log_path, f"cannot relaunch helper from temp: {exc}")
            return 8

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(str(os.getpid()), encoding="ascii")
    except OSError as exc:
        log(log_path, f"helper cannot create lock: {exc}")
        return 2

    try:
        log(log_path, f"helper started pid={args.pid} setup={setup} target={restart}")
        deadline = time.monotonic() + 120
        while pid_alive(args.pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        if pid_alive(args.pid):
            log(log_path, "target pid did not exit within 120 seconds")
            return 3
        time.sleep(1.0)

        # A manual relaunch of the same installed executable must not race the
        # installer. Wait briefly for it to finish rather than replacing files
        # under a live process.
        deadline = time.monotonic() + 30
        while target_running(restart) and time.monotonic() < deadline:
            time.sleep(0.5)
        if target_running(restart):
            log(log_path, "target executable is still running")
            return 4
        if not setup.is_file():
            log(log_path, f"installer missing: {setup}")
            return 5

        install_log = log_path.with_name("nodexy_install.log")
        command = [
            str(setup),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            "/LOG=" + str(install_log),
            # Установщик запоминает каталог по AppId и при тихом обновлении
            # подхватывает путь из реестра. Если рядом осталась старая
            # параллельная установка, файлы уезжали туда, а запускалась
            # прежняя копия — версия «не менялась». Каталог задаём явно и
            # отключаем страницу выбора, чтобы /DIR не игнорировался.
            "/DIR=" + str(target_dir),
            "/DISABLEDIRPAGE",
        ]
        log(log_path, "starting installer")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        # Этот процесс уже работает из %TEMP% (см. перенос выше), поэтому
        # файлы в каталоге приложения никто не удерживает.
        completed = subprocess.run(
            command,
            cwd=str(setup.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            check=False,
        )
        log(log_path, f"installer exit code={completed.returncode}")
        if completed.returncode != 0:
            return int(completed.returncode) or 1

        # Переходный период: до переименования в REDIS обновление могло
        # выполняться для Nodexy.exe. После установки имя могло измениться,
        # поэтому ждём любой из двух вариантов и запускаем тот, что есть.
        # Запускаем именно то, что установилось в целевой каталог: путь из
        # параметров мог устареть, если установщик переехал в другую папку.
        candidates = [
            target_dir / "REDIS.exe",
            target_dir / restart.name,
            restart,
            restart.with_name("REDIS.exe"),
        ]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not any(p.is_file() for p in candidates):
            time.sleep(0.25)
        restart = next((p for p in candidates if p.is_file()), None)
        if restart is None:
            log(log_path, f"updated executable missing in {target_dir}")
            return 6
        # Маркер установки снимается ДО запуска приложения: иначе новая копия
        # видит свежий lock и живой helper, считает, что установка идёт, и
        # сразу выходит — обновление оставалось бы без запущенного приложения.
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        subprocess.Popen(
            [str(restart)],
            cwd=str(restart.parent),
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log(log_path, "updated application launched")
        return 0
    except Exception as exc:
        log(log_path, f"helper failed: {type(exc).__name__}: {exc}")
        return 7
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--setup", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--restart", required=True)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--lock", required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
