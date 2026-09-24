"""engine_cache 引擎检测/证据持久缓存测试(带有效期)。

通过 monkeypatch.chdir 隔离 cwd,使 settings.json 落到临时目录;除真实两子进程
用例外均为纯文件/纯逻辑断言,不触发 COM。
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from file_toolbox.common import settings
from file_toolbox.core.batch_pdf import engine_cache
from file_toolbox.core.batch_pdf.constants import ENGINE_CACHE_TTL


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """隔离 cwd,使 settings 落到临时目录。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestSaveLoad:
    def test_roundtrip(self, isolated_cwd):
        """save 后 load 返回同值(verified_at 由模块写入)。"""
        assert engine_cache.save({"office": True, "wps": False}) is True
        assert engine_cache.load() == {"office": True, "wps": False}

    def test_load_missing_returns_none(self, isolated_cwd):
        assert engine_cache.load() is None

    def test_overwrite(self, isolated_cwd):
        """再次 save 覆盖旧记录。"""
        engine_cache.save({"office": True, "wps": True})
        engine_cache.save({"office": False, "wps": False})
        assert engine_cache.load() == {"office": False, "wps": False}


class TestTtl:
    def test_fresh_record_loaded(self, isolated_cwd):
        """verified_at 在有效期内 → 可读出。"""
        engine_cache.save({"office": True, "wps": False}, now=time.time() - ENGINE_CACHE_TTL + 60)
        assert engine_cache.load() == {"office": True, "wps": False}

    def test_stale_record_rejected(self, isolated_cwd):
        """verified_at 已过有效期 → None(到期重新兑现)。"""
        engine_cache.save({"office": True, "wps": False}, now=time.time() - ENGINE_CACHE_TTL - 1)
        assert engine_cache.load() is None

    def test_future_timestamp_rejected(self, isolated_cwd):
        """verified_at 落在未来(时钟回拨)→ 视为不合法,不长期采信旧记录。"""
        engine_cache.save({"office": True, "wps": False}, now=time.time() + 3600)
        assert engine_cache.load() is None


class TestCorruptionTolerance:
    @pytest.mark.parametrize(
        "record",
        [
            "not a dict",  # 非 dict
            42,
            None,
            {},  # 缺全部键
            {"office": True, "wps": False},  # 缺 verified_at
            {"office": True, "wps": False, "verified_at": "abc"},  # 时间戳非数字
            {"office": True, "wps": False, "verified_at": True},  # bool 是 int 子类,需排除
            {"office": 1, "wps": False, "verified_at": 123},  # 引擎值非 bool
            {"office": True, "wps": "yes", "verified_at": 123},
        ],
    )
    def test_invalid_records_rejected(self, isolated_cwd, record):
        """结构不合法的记录 → None,不抛。"""
        settings.set(engine_cache.CACHE_KEY, record)
        assert engine_cache.load() is None

    def test_extra_keys_tolerated(self, isolated_cwd):
        """额外键(未来 schema 扩展)不破坏兼容。"""
        settings.set(
            engine_cache.CACHE_KEY,
            {"office": True, "wps": False, "verified_at": time.time(), "future": 1},
        )
        assert engine_cache.load() == {"office": True, "wps": False}


class TestIoFailure:
    def test_load_settings_error_returns_none(self, isolated_cwd, monkeypatch):
        """settings.get 抛异常 → None(缓存只是加速,读失败降级)。"""
        monkeypatch.setattr(settings, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("io")))
        assert engine_cache.load() is None

    def test_save_settings_error_returns_false(self, isolated_cwd, monkeypatch):
        """settings.set 抛异常 → 返回 False 不抛(写失败不影响生成)。"""
        monkeypatch.setattr(settings, "set", lambda *a, **k: (_ for _ in ()).throw(OSError("io")))
        assert engine_cache.save({"office": True, "wps": False}) is False


class TestLoadWithReason:
    """load_with_reason:结构校验与时间校验拆分后的可诊断原因枚举。"""

    def test_hit(self, isolated_cwd):
        """有效期内的一致记录 → (记录, "hit")。"""
        engine_cache.save({"office": True, "wps": False})
        assert engine_cache.load_with_reason() == ({"office": True, "wps": False}, "hit")

    def test_expired(self, isolated_cwd):
        """结构合法但超 TTL → (None, "expired")。"""
        engine_cache.save({"office": True, "wps": False}, now=time.time() - ENGINE_CACHE_TTL - 1)
        assert engine_cache.load_with_reason() == (None, "expired")

    def test_future(self, isolated_cwd):
        """verified_at 落在未来(时钟回拨)→ (None, "future")。"""
        engine_cache.save({"office": True, "wps": False}, now=time.time() + 3600)
        assert engine_cache.load_with_reason() == (None, "future")

    def test_invalid(self, isolated_cwd):
        """结构不合法/损坏 → (None, "invalid")。"""
        settings.set(engine_cache.CACHE_KEY, {"office": 1, "wps": False, "verified_at": 123})
        assert engine_cache.load_with_reason() == (None, "invalid")

    def test_missing(self, isolated_cwd):
        """无记录 → (None, "missing")。"""
        assert engine_cache.load_with_reason() == (None, "missing")

    def test_io(self, isolated_cwd, monkeypatch):
        """settings.get 抛异常 → (None, "io")。"""
        monkeypatch.setattr(settings, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("io")))
        assert engine_cache.load_with_reason() == (None, "io")


# 子进程驱动:chdir 到指定数据根、直接赋值替换 _probe_registry/_try_detect(计数并
# 按参数返回指定真值)、按 argv 模式执行"检测"或"检测+record_engine_evidence",
# 把(探测计数、dispatch 尝试计数、get_engine_info 文案、load_with_reason 结果)以
# JSON 打到 stdout。写到 tmp_path,不进仓库。
_DRIVER_SOURCE = """import json
import os
import sys

repo_root, data_root, mode, office_flag, wps_flag = (
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1", sys.argv[5] == "1",
)
sys.path.insert(0, repo_root)
os.chdir(data_root)

from file_toolbox.core.batch_pdf import engine_cache
from file_toolbox.core.batch_pdf.engine_manager import EngineManager

probe_calls = []
dispatch_calls = []


def fake_probe(prog_id):
    probe_calls.append(prog_id)
    return (prog_id == "Word.Application" and office_flag) or (
        prog_id == "KWPS.Application" and wps_flag
    )


def fake_try_detect(prog_id, log):
    dispatch_calls.append(prog_id)
    return True


EngineManager._probe_registry = staticmethod(fake_probe)
EngineManager._try_detect = staticmethod(fake_try_detect)

em = EngineManager()
em._async_detect_body()
if mode == "detect+evidence":
    em.record_engine_evidence("office", True)

persisted, reason = engine_cache.load_with_reason()
print(
    json.dumps(
        {
            "probe_count": len(probe_calls),
            "dispatch_count": len(dispatch_calls),
            "info": em.get_engine_info(),
            "cache": persisted,
            "reason": reason,
        },
        ensure_ascii=False,
    ),
    flush=True,
)
"""


class TestCrossProcessEchoElimination:
    """真实两子进程回归(AC2):证据落盘跨进程复用,验证 Dispatch 零回声。"""

    def test_second_process_hits_cache_without_verification_dispatch(self, tmp_path):
        """进程1(检测+证据)落盘 settings.json;进程2(全新解释器,类状态天然全新)
        → 注册表探测照常发生、验证专用 Dispatch(_try_detect)计数==0、
        load_with_reason 为 hit、文案含"（缓存已验证）"。
        """
        pytest.importorskip("winreg")  # 非 Windows(无 winreg)跳过本用例
        repo_root = Path(__file__).resolve().parents[1]
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER_SOURCE, encoding="utf-8")

        def run_driver(mode: str) -> dict:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            try:
                proc = subprocess.run(
                    [sys.executable, str(driver), str(repo_root), str(tmp_path), mode, "1", "0"],
                    cwd=tmp_path,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise AssertionError(
                    f"driver({mode}) 超时 30s: stdout={e.stdout} stderr={e.stderr}"
                ) from e
            assert proc.returncode == 0, (
                f"driver({mode}) 退出码 {proc.returncode}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
            try:
                return json.loads(proc.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError) as e:
                raise AssertionError(
                    f"driver({mode}) 输出非 JSON: {proc.stdout!r}\nstderr={proc.stderr!r}"
                ) from e

        first = run_driver("detect+evidence")
        # 进程1:注册表检测 + 转换证据落盘;全程零验证 Dispatch
        assert (tmp_path / ".file_toolbox" / "settings.json").is_file()
        assert first["dispatch_count"] == 0
        assert first["cache"] == {"office": True, "wps": False}

        second = run_driver("detect")
        assert second["probe_count"] >= 1  # 新进程注册表探测照常发生
        assert second["dispatch_count"] == 0  # 关键:验证专用 Dispatch(_try_detect)== 0
        assert second["reason"] == "hit"
        assert "（缓存已验证）" in second["info"]
