"""settings 轻量 JSON 设置存储测试。"""

import json

import pytest

from file_toolbox.common import settings
from file_toolbox.common.settings import _settings_path


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """隔离 cwd,使 settings 落到临时目录。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestSettingsPath:
    def test_path_under_data_dir(self, isolated_cwd):
        """settings 路径 = .file_toolbox/settings.json。"""
        p = _settings_path()
        assert p.name == "settings.json"
        assert p.parent.name == ".file_toolbox"


class TestGetSet:
    def test_get_missing_returns_default(self, isolated_cwd):
        assert settings.get("nope") is None
        assert settings.get("nope", "fallback") == "fallback"

    def test_set_then_get(self, isolated_cwd):
        settings.set("gh_proxy", "https://ghproxy.com")
        assert settings.get("gh_proxy") == "https://ghproxy.com"

    def test_overwrite(self, isolated_cwd):
        settings.set("k", 1)
        settings.set("k", 2)
        assert settings.get("k") == 2

    def test_other_keys_preserved(self, isolated_cwd):
        settings.set("a", 1)
        settings.set("b", 2)
        assert settings.get("a") == 1
        assert settings.get("b") == 2

    def test_persists_to_file(self, isolated_cwd):
        settings.set("gh_proxy", "https://x.com")
        data = json.loads((_settings_path()).read_text(encoding="utf-8"))
        assert data["gh_proxy"] == "https://x.com"


class TestCorruptionTolerance:
    def test_corrupt_json_returns_default(self, isolated_cwd):
        """settings.json 损坏 → get 返回 default 不抛。"""
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text("{not valid json", encoding="utf-8")
        assert settings.get("anything", "d") == "d"

    def test_set_after_corruption_rewrites_clean(self, isolated_cwd):
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text("garbage", encoding="utf-8")
        settings.set("k", "v")
        assert settings.get("k") == "v"

    @pytest.mark.parametrize("payload", ["[1, 2, 3]", '"a string"', "42", "true", "null"])
    def test_non_dict_valid_json_returns_default(self, isolated_cwd, payload):
        """合法但非 dict 的 JSON(列表/字符串/数字/布尔/null)→ _load 回退 {},get 返回 default。

        回归保护:isinstance(data, dict) 守卫若被移除,后续 .get 会 AttributeError。
        """
        _settings_path().parent.mkdir(parents=True, exist_ok=True)
        _settings_path().write_text(payload, encoding="utf-8")
        assert settings.get("anything", "d") == "d"


# =====================================================================================
# Issue #77 回归:并发 set 不同 key 不互相覆盖、唯一临时文件、IO 失败不覆盖旧文件。
# =====================================================================================
import multiprocessing  # noqa: E402
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402


def _spawn_set_child(key: str) -> None:
    """spawn 子进程:按 CLI 数据根策略(cwd-scoped)写一个设置 key。"""
    settings.set(key, 1)


class TestConcurrentSet:
    def test_threads_set_different_keys_all_preserved(self, isolated_cwd, store_lock_probe):
        """第一个 set 完成读改尚未保存时,第二个 set 必须等待整个事务。"""
        reached_save = threading.Event()
        proceed = threading.Event()
        contended, progressed = store_lock_probe
        original = settings._save

        def gated_save(data):
            if "a" in data and "b" not in data:
                reached_save.set()
                assert proceed.wait(5)
            original(data)

        with patch.object(settings, "_save", side_effect=gated_save), ThreadPoolExecutor(2) as pool:
            writer = pool.submit(settings.set, "a", 1)
            try:
                assert reached_save.wait(5)
                contender = pool.submit(settings.set, "b", 1)
                contender.add_done_callback(lambda _: progressed.set())
                assert progressed.wait(5), "竞争者必须到达真实锁竞争或完成事务"
                assert contended.is_set(), "set 读取与保存之间必须保持事务锁"
                assert not contender.done()
            finally:
                proceed.set()
            writer.result(timeout=5)
            contender.result(timeout=5)
        assert settings.get("a") == 1
        assert settings.get("b") == 1

    def test_spawn_two_processes_set_different_keys_all_preserved(self, isolated_cwd):
        """真实双进程 spawn 并发 set 不同 key:两个 key 都保留(跨进程锁互斥)。"""
        ctx = multiprocessing.get_context("spawn")
        children = [ctx.Process(target=_spawn_set_child, args=(k,)) for k in ("a", "b")]
        for child in children:
            child.start()
        try:
            for child in children:
                child.join(timeout=20)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
        assert [child.exitcode for child in children] == [0, 0]
        assert settings.get("a") == 1
        assert settings.get("b") == 1

    def test_no_fixed_or_residual_temp_files(self, isolated_cwd):
        """写路径不再使用固定 settings.tmp;事务后目录无 .tmp 残留。"""
        settings.set("k", "v")
        data_dir = _settings_path().parent
        assert not (data_dir / "settings.tmp").exists()
        assert not list(data_dir.glob("*.tmp"))
        # 稳定 sidecar 锁文件保留(与临时文件区分)
        assert (data_dir / "settings.json.lock").exists()


class TestWriteFailurePreservation:
    def test_replace_failure_preserves_old_and_cleans_tmp(self, isolated_cwd):
        """replace 失败:异常传播,旧文件保留,本次临时文件被清理。"""
        p = _settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"old": 1}', encoding="utf-8")
        with (
            patch(
                "file_toolbox.common.settings.os.replace", side_effect=OSError("injected replace")
            ),
            pytest.raises(OSError, match="injected replace"),
        ):
            settings.set("new", 2)
        assert json.loads(p.read_text(encoding="utf-8")) == {"old": 1}
        assert not list(p.parent.glob("*.tmp"))

    def test_read_permission_error_propagates_without_overwrite(self, isolated_cwd):
        """权限等 IO 读取失败不得被当作空设置:set 传播异常,旧文件不被覆盖。

        旧实现 _load 吞掉 OSError 返回 {},set 会用 {key: value} 重写整个文件。
        """
        p = _settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"old": 1}', encoding="utf-8")
        with (
            patch.object(Path, "read_text", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError, match="denied"),
        ):  # noqa: SIM117
            settings.set("new", 2)
        assert json.loads(p.read_text(encoding="utf-8")) == {"old": 1}
