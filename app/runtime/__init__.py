"""Runtime-пакет Nodexy: запуск, один экземпляр и жизненный цикл UI."""

from .startup import InstanceGuard, create_application

__all__ = ["InstanceGuard", "create_application"]
