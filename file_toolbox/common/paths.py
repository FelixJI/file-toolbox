"""工具箱持久数据路径。

CLI 默认保持 cwd-scoped ``.file_toolbox/``；GUI 入口显式切换为程序目录 policy
(便携发行形态下数据跟随程序所在目录，而不是用户 home)。
业务模块只通过本文件的 ``get_*_dir`` Interface 访问路径，不感知启动形态。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_DIR_NAME = ".file_toolbox"


class DataRootPolicy(Protocol):
    """GUI/CLI 持久数据根 Adapter。"""

    def data_root(self) -> Path:
        """返回 ``.file_toolbox`` 目录，不负责创建。"""


@dataclass(frozen=True)
class CliDataRootPolicy:
    """CLI 数据跟随每次调用时的工作目录。"""

    def data_root(self) -> Path:
        return Path.cwd() / _DIR_NAME


@dataclass(frozen=True)
class GuiDataRootPolicy:
    """GUI 数据固定在程序目录(Velopack ``current/`` 之外)，随便携包整体携带。"""

    base_dir: Path

    def data_root(self) -> Path:
        return self.base_dir / _DIR_NAME


_POLICY: ContextVar[DataRootPolicy | None] = ContextVar(
    "file_toolbox_data_root_policy", default=None
)


@contextmanager
def use_data_root_policy(policy: DataRootPolicy) -> Iterator[None]:
    """在当前执行上下文中使用指定 data-root policy。"""

    token = _POLICY.set(policy)
    try:
        yield
    finally:
        _POLICY.reset(token)


def _data_dir() -> Path:
    """当前 policy 的数据根目录。不创建，供其它函数组合。"""

    policy = _POLICY.get()
    return (policy or CliDataRootPolicy()).data_root()


def current_data_root() -> Path:
    """当前 policy 的数据根目录(只读,不创建)。单实例服务等身份派生场景使用。"""

    return _data_dir()


def get_data_dir() -> Path:
    """获取(并创建)数据根目录。供模板等持久化文件落位。"""
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backup_dir() -> Path:
    """获取(并创建)备份目录。"""
    d = _data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_history_dir() -> Path:
    """获取(并创建)历史目录。"""
    d = _data_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    """获取（并创建）应用日志目录。"""
    d = _data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
