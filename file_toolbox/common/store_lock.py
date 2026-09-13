"""目标文件级跨进程事务锁。

同一持久化文件(history 的 ``<tool>.jsonl``、``settings.json``)可能被多个进程
同时访问:CLI 每次调用各自成进程,GUI 与 CLI 也可能共存。本模块按「规范化后的
目标路径」提供两级互斥:

1. 进程内:每条锁身份一把 ``threading.Lock``,先串行化同进程线程,不依赖 OS 锁
   对同进程重复获取的平台差异(Windows ``msvcrt`` 按 fd 加锁,同进程两个 fd 之间
   同样互斥,但行为契约跨平台不一致,故以线程锁为先)。
2. 进程间:目标同目录稳定 sidecar ``<target>.lock`` 文件,Windows 用
   ``msvcrt.locking``,POSIX 用 ``fcntl.flock``;非阻塞获取 + 有界轮询,超时抛
   ``TimeoutError``,权限等非竞争 IO 错误原样传播,不会默默无锁继续。

锁文件创建后不删除:反复创建/删除会让不同进程打开的句柄指向不同 inode/文件体,
互斥失效。进程正常退出由 OS 释放文件锁,残留的空 ``.lock`` 文件无需清理。
"""

from __future__ import annotations

import errno
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:  # pragma: no cover - POSIX 后端,win32 CI 不可达
    import fcntl

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.01

# 「锁被他人持有」类 errno:只有这些进入轮询等待,其余 IO 错误立即传播。
# Windows msvcrt.locking 竞争抛 EACCES/EDEADLK;POSIX flock 竞争抛 EAGAIN
# (BlockingIOError 是其子类)。
_CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EDEADLK, errno.EAGAIN, errno.EWOULDBLOCK})

# 进程内按锁身份共享的线程锁表;表自身的并发访问由 _REGISTRY_GUARD 保护。
# 锁条目不回收:每进程涉及的持久化文件数量有限(各工具 history + settings)。
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_REGISTRY_GUARD = threading.Lock()


def lock_key(target: Path) -> str:
    """目标文件的锁身份:绝对化 + POSIX 分隔符统一;Windows 再大小写归一。

    相对/绝对混用、``.``/``..`` 段与 Windows 大小写别名必须派生同一把锁。
    ``resolve()`` 对存在的路径返回文件系统真实形式(含真实大小写),对不存在
    的尾段保留输入形式,大小写归一兜底两侧。
    """
    key = target.resolve().as_posix()
    if sys.platform == "win32":
        key = key.casefold()
    return key


def lock_path_for(target: Path) -> Path:
    """目标文件对应的稳定 sidecar 锁文件路径(不删除、不轮换)。"""
    return target.with_name(target.name + ".lock")


@contextmanager
def file_transaction_lock(
    target: Path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> Iterator[None]:
    """按目标路径获取整个读-改-写事务的互斥锁(线程 + 跨进程)。

    公共持久化事务都在本上下文内完成读、分配与写;内部 helper 不得再嵌套
    获取(线程锁不可重入,嵌套会立即死锁并被测试暴露)。超时抛
    ``TimeoutError``,权限等 IO 错误原样传播。
    """
    key = lock_key(target)
    thread_lock = _thread_lock_for(key)
    if not thread_lock.acquire(timeout=timeout):
        raise TimeoutError(f"等待文件事务锁超时(进程内): {target}")
    try:
        fd = _acquire_os_lock(lock_path_for(target), timeout)
        try:
            yield
        finally:
            _release_os_lock(fd)
    finally:
        thread_lock.release()


def _thread_lock_for(key: str) -> threading.Lock:
    with _REGISTRY_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


def _acquire_os_lock(lock_file: Path, timeout: float) -> int:
    """创建/打开锁文件并以非阻塞方式加锁,竞争时有界轮询。

    返回持有锁的 fd,调用方负责释放;超时前关闭 fd 并抛 ``TimeoutError``,
    非竞争 IO 错误(如目录不可写)关闭 fd 后原样传播。
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0))
    acquired = False
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _lock_region_nonblocking(fd)
                acquired = True
                return fd
            except OSError as exc:
                if exc.errno not in _CONTENTION_ERRNOS:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待文件事务锁超时(跨进程): {lock_file}") from exc
                time.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        if not acquired:
            os.close(fd)


def _release_os_lock(fd: int) -> None:
    """释放区域锁并关闭句柄;解锁失败由 close 兜底(OS 关句柄即释放)。"""
    try:
        _unlock_region(fd)
    except OSError:  # pragma: no cover - 正常路径不解锁失败,防御进程退出竞态
        logger.warning("文件事务锁解锁失败,将随句柄关闭释放", exc_info=True)
    finally:
        os.close(fd)


def _lock_region_nonblocking(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover - POSIX 后端,win32 CI 不可达
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_region(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:  # pragma: no cover - POSIX 后端,win32 CI 不可达
        fcntl.flock(fd, fcntl.LOCK_UN)
