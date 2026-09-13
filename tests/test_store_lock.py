"""store_lock 跨进程事务锁测试。

覆盖锁身份规范化(相对/绝对、Windows 大小写别名)、线程/进程两级互斥、
有界超时、非竞争 IO 错误传播与锁文件生命周期。
"""

from __future__ import annotations

import multiprocessing
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from file_toolbox.common import store_lock
from file_toolbox.common.store_lock import file_transaction_lock, lock_key, lock_path_for

_WIN32 = sys.platform == "win32"


def _child_lock_probe(target, child_saw_timeout, parent_released) -> None:
    """spawn 子进程:先证明父进程持锁时自己超时,再证明释放后可获取。"""
    try:
        with file_transaction_lock(target, timeout=0.3):
            pass
    except TimeoutError:
        child_saw_timeout.set()
        assert parent_released.wait(10)
        with file_transaction_lock(target, timeout=5.0):
            pass


def _child_hold_probe(target, holding, release) -> None:
    """spawn 子进程:取得锁后保持到 release,供父进程验证跨进程超时。"""
    with file_transaction_lock(target, timeout=5.0):
        holding.set()
        assert release.wait(15)


@contextmanager
def _held_lock(target: Path, timeout: float = 5.0):
    """在当前线程持有 target 事务锁直到上下文退出。"""
    with file_transaction_lock(target, timeout=timeout):
        yield


class TestLockKeyNormalization:
    def test_relative_and_absolute_share_key(self, tmp_path, monkeypatch):
        """相对路径与绝对路径指向同一文件 → 同一锁身份。"""
        monkeypatch.chdir(tmp_path)
        assert lock_key(Path("sub/data.jsonl")) == lock_key(tmp_path / "sub" / "data.jsonl")

    def test_dot_segments_share_key(self, tmp_path, monkeypatch):
        """`.`/`..` 段归一后与直接路径同身份。"""
        monkeypatch.chdir(tmp_path)
        assert lock_key(Path("sub/../sub/./data.jsonl")) == lock_key(
            tmp_path / "sub" / "data.jsonl"
        )

    @pytest.mark.skipif(not _WIN32, reason="Windows 路径大小写别名归一")
    def test_windows_case_alias_share_key(self, tmp_path):
        """Windows 大小写不敏感:同一存在目录的大小写变体 → 同一锁身份。"""
        real_dir = tmp_path / "Data"
        real_dir.mkdir()
        alias = Path(str(real_dir).swapcase())
        assert str(alias) != str(real_dir)
        assert lock_key(alias / "f.jsonl") == lock_key(real_dir / "f.jsonl")

    def test_different_targets_differ(self, tmp_path):
        assert lock_key(tmp_path / "a.jsonl") != lock_key(tmp_path / "b.jsonl")


class TestInProcessMutualExclusion:
    def test_second_thread_times_out_until_release(self, tmp_path):
        """线程 A 持锁期间,线程 B 以短超时获取 → TimeoutError;释放后可获取。"""
        target = tmp_path / "f.bin"
        held = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with _held_lock(target):
                held.set()
                assert release.wait(5)

        thread = threading.Thread(target=holder)
        thread.start()
        try:
            assert held.wait(5)
            with (
                pytest.raises(TimeoutError),
                file_transaction_lock(target, timeout=0.2),
            ):  # noqa: SIM117
                pass
        finally:
            release.set()
            thread.join(timeout=5)
        assert not thread.is_alive()
        with _held_lock(target, timeout=1.0):
            pass  # 释放后立即可重入获取

    def test_different_targets_do_not_block_each_other(self, tmp_path):
        """不同目标文件互不阻塞(A 持 f1 时 f2 立即可获取)。"""
        with _held_lock(tmp_path / "f1.bin"), _held_lock(tmp_path / "f2.bin", timeout=1.0):
            pass

    def test_lock_file_persists_after_release(self, tmp_path):
        """锁文件是稳定 sidecar:事务后保留(不删除,避免句柄分裂)。"""
        target = tmp_path / "f.bin"
        with _held_lock(target):
            pass
        assert lock_path_for(target).exists()


class TestErrorPropagation:
    def test_open_failure_propagates(self, tmp_path):
        """锁文件创建失败(如权限)原样传播,不静默无锁继续。"""
        with (
            patch.object(store_lock.os, "open", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError, match="denied"),
            file_transaction_lock(tmp_path / "f.bin"),
        ):  # noqa: SIM117
            pass

    def test_non_contention_lock_error_propagates_immediately(self, tmp_path):
        """非竞争类加锁错误(非 EACCES/EAGAIN 集合)立即传播,不进入轮询等待。"""
        import errno

        side_effect = OSError(errno.EIO, "io error")
        assert side_effect.errno not in store_lock._CONTENTION_ERRNOS
        with (
            patch.object(store_lock, "_lock_region_nonblocking", side_effect=side_effect),
            pytest.raises(OSError, match="io error"),
            file_transaction_lock(tmp_path / "f.bin", timeout=5.0),
        ):  # noqa: SIM117
            pass


class TestCrossProcess:
    def test_child_process_cannot_enter_while_parent_holds(self, tmp_path):
        """父进程持锁期间,spawn 子进程短超时获取 → 子进程观测 TimeoutError;
        父进程释放后子进程能成功获取并正常退出。"""
        target = tmp_path / "f.bin"
        ctx = multiprocessing.get_context("spawn")
        child_saw_timeout = ctx.Event()
        parent_released = ctx.Event()

        proc = ctx.Process(
            target=_child_lock_probe, args=(target, child_saw_timeout, parent_released)
        )
        proc.start()
        try:
            with _held_lock(target):
                assert child_saw_timeout.wait(10), "子进程应在父进程持锁期间超时"
            parent_released.set()
            proc.join(timeout=15)
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join()
                pytest.fail("子进程超时未退出")
        assert proc.exitcode == 0

    def test_parent_times_out_while_child_holds(self, tmp_path):
        """子进程持锁期间,父进程短超时获取 → TimeoutError(有界等待后明确失败);
        子进程释放后父进程可正常获取。"""
        target = tmp_path / "f.bin"
        ctx = multiprocessing.get_context("spawn")
        child_holding = ctx.Event()
        release = ctx.Event()

        proc = ctx.Process(target=_child_hold_probe, args=(target, child_holding, release))
        proc.start()
        try:
            assert child_holding.wait(15), "子进程应先取得锁"
            with (
                pytest.raises(TimeoutError),
                file_transaction_lock(target, timeout=0.4),
            ):
                pass
        finally:
            release.set()
            proc.join(timeout=15)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            pytest.fail("子进程超时未退出")
        assert proc.exitcode == 0
        with file_transaction_lock(target, timeout=5.0):
            pass  # 子进程退出释放后可正常获取
