"""engine_cache 引擎验证持久缓存测试(带有效期)。

通过 monkeypatch.chdir 隔离 cwd,使 settings.json 落到临时目录;所有用例均为
纯文件/纯逻辑断言,不触发 COM。
"""

import time

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
