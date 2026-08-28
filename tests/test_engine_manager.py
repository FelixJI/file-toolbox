"""EngineManager 注册表探测单元测试。

不触发真实 COM Dispatch,仅用 monkeypatch 替换 winreg。这些测试直接用 winreg 的
真实模块对象做 monkeypatch,故仅在 Windows(winreg 存在)上有效;非 Windows 跳过
(产品本身的 _probe_registry 已对 ImportError 做了回退处理)。
"""

import time
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.batch_pdf import engine_cache
from file_toolbox.core.batch_pdf.engine_manager import EngineManager


@pytest.fixture
def engine_cache_stub(monkeypatch):
    """隔离持久引擎缓存:load 可编程返回,save 只记录不落盘。

    没有此 stub 时 ensure_verified 会真读写 cwd 下 .file_toolbox/settings.json,
    既污染仓库工作树,也让断言依赖文件系统。
    """
    state = {"load": None, "saved": []}
    monkeypatch.setattr(engine_cache, "load", lambda *a, **k: state["load"])
    monkeypatch.setattr(
        engine_cache, "save", lambda engines, *a, **k: state["saved"].append(dict(engines)) or True
    )
    return state


def test_probe_registry_returns_true_when_key_exists(monkeypatch):
    """HKCR 下存在 ProgID → 返回 True。"""
    winreg = pytest.importorskip("winreg")

    def fake_open_key(root, subkey, *args, **kwargs):
        if subkey.lower() == "word.application":
            return object()  # 假的 key handle
        raise FileNotFoundError(subkey)

    monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is True
    assert EngineManager._probe_registry("KWPS.Application") is False


def test_probe_registry_returns_false_on_file_not_found(monkeypatch):
    winreg = pytest.importorskip("winreg")

    def raise_fnf(root, subkey, *args, **kwargs):
        raise FileNotFoundError(subkey)

    monkeypatch.setattr(winreg, "OpenKey", raise_fnf)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is False


def test_probe_registry_returns_false_on_os_error(monkeypatch):
    """权限错误等 OSError 也视为不可用。"""
    winreg = pytest.importorskip("winreg")

    def raise_os(root, subkey, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(winreg, "OpenKey", raise_os)
    monkeypatch.setattr(winreg, "CloseKey", lambda h: None)

    assert EngineManager._probe_registry("Word.Application") is False


def test_detect_uses_registry_by_default(monkeypatch):
    """force_refresh=False(默认)走注册表,不调 _try_detect。"""
    # 清缓存避免串测
    EngineManager._cached_engines = None
    em = EngineManager()

    calls = []
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: calls.append(prog_id) or True
    )
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda *a, **k: pytest.fail("不应调用真 Dispatch")
    )

    result = em._detect_available_engines(force_refresh=False)
    assert result == {"office": True, "wps": True}
    assert "Word.Application" in calls
    assert "KWPS.Application" in calls


def test_detect_force_refresh_uses_real_dispatch(monkeypatch):
    """force_refresh=True 走 _try_detect(真 Dispatch),不调注册表。"""
    EngineManager._cached_engines = None
    em = EngineManager()

    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda *a, **k: pytest.fail("force_refresh 不应走注册表")
    )
    monkeypatch.setattr(EngineManager, "_try_detect", lambda *a, **k: True)

    result = em._detect_available_engines(force_refresh=True)
    assert result == {"office": True, "wps": True}


# ---------------------------------------------------------------------------
# ensure_verified:进程内一次性兑现(只检测缓存判定可用的引擎,_verified 去重)
# ---------------------------------------------------------------------------


def test_ensure_verified_only_verifies_available_engines(monkeypatch, engine_cache_stub):
    """首次兑现:只对缓存判定可用的引擎做真 Dispatch(不双引擎全量启动)。

    缓存 office=True、wps=False → 只 Dispatch Word.Application,不碰 KWPS。
    """
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    em = EngineManager()

    detected = []
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda prog_id, log: detected.append(prog_id) or True
    )

    em.ensure_verified()

    assert detected == ["Word.Application"]  # 只兑现 office
    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": True, "wps": False}
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_dedupes_within_process(monkeypatch, engine_cache_stub):
    """_verified 标志:第二次 ensure_verified 直接返回,不再 Dispatch。"""
    EngineManager._cached_engines = {"office": True, "wps": True}
    EngineManager._verified = False
    em = EngineManager()

    calls = []
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda prog_id, log: calls.append(prog_id) or True
    )

    em.ensure_verified()
    em.ensure_verified()  # 第二次应短路

    assert len(calls) == 2  # 仅首次两个(office + wps),第二次零 Dispatch
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_no_op_when_no_engines(monkeypatch, engine_cache_stub):
    """缓存为空 → 先补注册表预筛;预筛判定无可用引擎 → 不 Dispatch,仍置 _verified。"""
    EngineManager._cached_engines = None
    EngineManager._verified = False
    em = EngineManager()

    monkeypatch.setattr(EngineManager, "_probe_registry", lambda prog_id: False)
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda *a, **k: pytest.fail("无可兑现引擎不应 Dispatch")
    )

    em.ensure_verified()

    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": False, "wps": False}
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_updates_cache_with_dispatch_result(monkeypatch, engine_cache_stub):
    """兑现结果(Dispatch 失败 → False)精确写回缓存,不污染其他引擎键。"""
    EngineManager._cached_engines = {"office": True, "wps": True}
    EngineManager._verified = False
    em = EngineManager()

    # office 兑现成功(True),wps 兑现失败(False)
    def fake_detect(prog_id, log):
        return prog_id == "Word.Application"

    monkeypatch.setattr(EngineManager, "_try_detect", fake_detect)

    em.ensure_verified()

    assert EngineManager._cached_engines == {"office": True, "wps": False}
    EngineManager._cached_engines = None
    EngineManager._verified = False


# ---------------------------------------------------------------------------
# ensure_verified × engine_cache 持久缓存:有效期内且与注册表一致 → 跨进程零 Dispatch
# ---------------------------------------------------------------------------


def test_ensure_verified_adopts_matching_persistent_cache(monkeypatch, engine_cache_stub):
    """持久缓存有效期内且与实时注册表探测一致 → 直接采信,零 Dispatch、不回写。"""
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    engine_cache_stub["load"] = {"office": True, "wps": False}
    em = EngineManager()

    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda *a, **k: pytest.fail("持久缓存命中不应 Dispatch")
    )

    em.ensure_verified()

    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": True, "wps": False}
    assert engine_cache_stub["saved"] == []
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_rejects_mismatched_persistent_cache(monkeypatch, engine_cache_stub):
    """持久缓存与实时注册表不一致(安装变化)→ 不采信,重新兑现并回写新结果。"""
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    engine_cache_stub["load"] = {"office": False, "wps": False}  # 旧结论:office 不可用
    em = EngineManager()

    monkeypatch.setattr(EngineManager, "_try_detect", lambda prog_id, log: True)

    em.ensure_verified()

    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": True, "wps": False}
    assert engine_cache_stub["saved"] == [{"office": True, "wps": False}]
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_saves_result_after_dispatch(monkeypatch, engine_cache_stub):
    """无持久缓存(首跑/过期)→ 兑现结果回写持久缓存,供后续进程采信。"""
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    engine_cache_stub["load"] = None
    em = EngineManager()

    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda prog_id, log: prog_id == "Word.Application"
    )

    em.ensure_verified()

    assert engine_cache_stub["saved"] == [{"office": True, "wps": False}]
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_save_failure_is_not_fatal(monkeypatch, engine_cache_stub):
    """持久缓存写入失败 → 仅告警降级(本进程内缓存仍生效),不抛异常。"""
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    engine_cache_stub["load"] = None
    em = EngineManager()
    monkeypatch.setattr(engine_cache, "save", lambda *a, **k: False)
    monkeypatch.setattr(EngineManager, "_try_detect", lambda prog_id, log: True)

    em.ensure_verified()  # 不抛

    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": True, "wps": False}
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_probes_registry_when_cache_empty(monkeypatch, engine_cache_stub):
    """缓存未填充(未经启动探测直接生成)→ 先补注册表预筛,再按预筛结果兑现。"""
    EngineManager._cached_engines = None
    EngineManager._verified = False
    em = EngineManager()

    probed = []
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: probed.append(prog_id) or True
    )
    detected = []
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda prog_id, log: detected.append(prog_id) or False
    )

    em.ensure_verified()

    assert "Word.Application" in probed and "KWPS.Application" in probed
    assert detected == ["Word.Application", "KWPS.Application"]  # 预筛可用 → 逐个兑现
    assert EngineManager._cached_engines == {"office": False, "wps": False}
    assert engine_cache_stub["saved"] == [{"office": False, "wps": False}]
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_ensure_verified_cross_process_roundtrip(tmp_path, monkeypatch):
    """集成回归:首跑兑现并落盘 → 第二个"进程"(重置类状态)命中持久缓存,零 Dispatch。

    在旧实现(仅进程内缓存)上本测试必败:第二个 ensure_verified 会再次触发
    _try_detect → pytest.fail。走真实 engine_cache + settings 文件(chdir 隔离)。
    """
    monkeypatch.chdir(tmp_path)

    # 第一个"进程":预筛 office 可用 → 真 Dispatch 兑现(此处 stub 成功)→ 落盘
    EngineManager._cached_engines = {"office": True, "wps": False}
    EngineManager._verified = False
    monkeypatch.setattr(EngineManager, "_try_detect", lambda prog_id, log: True)
    EngineManager().ensure_verified()
    assert (tmp_path / ".file_toolbox" / "settings.json").is_file()

    # 第二个"进程":重置进程内状态;注册表预筛得到相同结果
    EngineManager._cached_engines = None
    EngineManager._verified = False
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: prog_id == "Word.Application"
    )
    monkeypatch.setattr(
        EngineManager, "_try_detect", lambda *a, **k: pytest.fail("持久缓存应命中,不应 Dispatch")
    )
    EngineManager().ensure_verified()

    assert EngineManager._verified is True
    assert EngineManager._cached_engines == {"office": True, "wps": False}
    EngineManager._cached_engines = None
    EngineManager._verified = False


def test_async_detect_body_uses_registry_probe_not_dispatch(monkeypatch):
    """回归:启动异步检测必须走注册表(force_refresh=False),不应触发真 Dispatch。

    此前 detect_engines_async 的 worker 以 force_refresh=True 调用,每次打开对话框都
    Dispatch Word/WPS,违背注册表快速探测的设计目标。worker 体已抽到
    _async_detect_body,可直接同步断言。
    """
    EngineManager._cached_engines = None  # 清缓存避免直接命中
    em = EngineManager()

    detect_calls = []
    try_calls = []

    def _spy_detect(self, force_refresh=False):
        detect_calls.append(force_refresh)
        return {"office": True, "wps": False}

    monkeypatch.setattr(EngineManager, "_detect_available_engines", _spy_detect)
    monkeypatch.setattr(
        EngineManager,
        "_try_detect",
        lambda *a, **k: try_calls.append(a) or pytest.fail("启动检测不应走真 Dispatch"),
    )

    # 回调应被调用,参数为 get_engine_info(use_cache=True) 的返回字符串
    captured = {}
    em._async_detect_body(callback=lambda info: captured.setdefault("info", info))

    assert len(detect_calls) == 1
    assert detect_calls[0] is False  # 关键:force_refresh=False(注册表探测)
    assert try_calls == []  # 未触发真 Dispatch
    assert "info" in captured and isinstance(captured["info"], str)


# ---------------------------------------------------------------------------
# 补充覆盖:_probe_registry ImportError 分支、缓存命中、get_engine_info 各分支、
# _get_prog_id auto 选择、_prog_ids_to_try、init_* 非 win32 抛错、_async_detect_body except。
# 均纯逻辑/mock,不触发真实 COM。
# ---------------------------------------------------------------------------


def test_probe_registry_import_error_returns_false(monkeypatch):
    """winreg import 失败(非 win32)→ 返回 False。

    覆盖 engine_manager.py 行 100-101。通过让内置 __import__ 对 winreg 抛 ImportError
    模拟非 Windows 环境(Linux CI 上 winreg 本就不存在,但确保该分支被显式覆盖)。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("simulated non-windows")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert EngineManager._probe_registry("Word.Application") is False


def test_detect_returns_cache_when_present():
    """已缓存且非 force_refresh → 直接返回缓存,不重新探测。

    覆盖 engine_manager.py 行 115-116。
    """
    cached = {"office": True, "wps": False}
    EngineManager._cached_engines = cached
    em = EngineManager()
    assert em._detect_available_engines() is cached
    # 清理,避免污染后续测试
    EngineManager._cached_engines = None


def test_get_engine_info_both_engines():
    """office + wps 都可用 → 信息含两者。

    覆盖 engine_manager.py 行 148-151, 156。
    """
    EngineManager._cached_engines = {"office": True, "wps": True}
    em = EngineManager()
    info = em.get_engine_info()
    assert "MS Office" in info
    assert "WPS" in info
    EngineManager._cached_engines = None


def test_get_engine_info_wps_only():
    """仅 wps 可用 → 信息只含 WPS。

    覆盖 engine_manager.py 行 148-151 的 wps 分支。
    """
    EngineManager._cached_engines = {"office": False, "wps": True}
    em = EngineManager()
    info = em.get_engine_info()
    assert "WPS" in info
    assert "MS Office" not in info
    EngineManager._cached_engines = None


def test_get_engine_info_none_available():
    """都不可用 → '未检测到Office软件'。

    覆盖 engine_manager.py 行 153-154。
    """
    EngineManager._cached_engines = {"office": False, "wps": False}
    em = EngineManager()
    assert em.get_engine_info() == "未检测到Office软件"
    EngineManager._cached_engines = None


def test_get_engine_info_detecting_when_no_cache():
    """无缓存且 use_cache=True → '正在检测...'。

    覆盖 engine_manager.py 行 142-143。
    """
    EngineManager._cached_engines = None
    em = EngineManager()
    assert em.get_engine_info(use_cache=True) == "正在检测可用引擎..."
    EngineManager._cached_engines = None


def test_get_prog_id_auto_prefers_ms_office(monkeypatch):
    """auto 引擎:office 可用 → 返回 MS Office ProgID。

    覆盖 engine_manager.py 行 219-223。
    """
    EngineManager._cached_engines = None
    em = EngineManager()
    monkeypatch.setattr(em, "_detect_available_engines", lambda **k: {"office": True, "wps": True})
    assert em._get_prog_id("word") == "Word.Application"
    assert em._get_prog_id("excel") == "Excel.Application"
    assert em._get_prog_id("ppt") == "PowerPoint.Application"


def test_get_prog_id_auto_wps_only(monkeypatch):
    """auto 引擎:仅 wps 可用 → 返回 WPS ProgID。

    覆盖 engine_manager.py 行 221-222。
    """
    em = EngineManager()
    monkeypatch.setattr(em, "_detect_available_engines", lambda **k: {"office": False, "wps": True})
    assert em._get_prog_id("word") == "KWPS.Application"


def test_get_prog_id_explicit_wps():
    """显式 engine=wps → 返回 WPS ProgID(不看检测结果)。

    覆盖 engine_manager.py 行 224-225。
    """
    em = EngineManager()
    assert em._get_prog_id("excel", engine="wps") == "Ket.Application"


def test_get_prog_id_explicit_ms_office():
    """显式非 auto 非 wps → 返回 MS Office ProgID。

    覆盖 engine_manager.py 行 226。
    """
    em = EngineManager()
    assert em._get_prog_id("ppt", engine="office") == "PowerPoint.Application"


def test_prog_ids_to_try_wps_engine():
    """engine=wps → [wps, ms] 顺序(优先 WPS,回退 MS)。

    覆盖 engine_manager.py 行 231-232。
    """
    em = EngineManager()
    assert em._prog_ids_to_try("word", "wps") == ["KWPS.Application", "Word.Application"]


def test_prog_ids_to_try_auto_engine():
    """engine=auto → [ms, wps] 顺序(优先 MS,回退 WPS)。

    覆盖 engine_manager.py 行 233-234。
    """
    em = EngineManager()
    assert em._prog_ids_to_try("excel", "auto") == ["Excel.Application", "Ket.Application"]
    assert em._prog_ids_to_try("ppt", "office") == ["PowerPoint.Application", "KWPP.Application"]


def test_async_detect_body_swallows_exception(monkeypatch):
    """_detect_available_engines 抛异常 → except 捕获并记日志,不波及调用线程。

    覆盖 engine_manager.py 行 210-211。
    """
    em = EngineManager()
    monkeypatch.setattr(
        em, "_detect_available_engines", lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    # 不抛异常即通过(异常被吞)
    em._async_detect_body(callback=lambda info: None)


def test_init_word_raises_on_non_windows(monkeypatch):
    """非 win32 平台 init_word → RuntimeError。

    覆盖 engine_manager.py 行 278(经 _init_office_app 行 238-239)。
    """
    em = EngineManager()
    monkeypatch.setattr(
        "file_toolbox.core.batch_pdf.engine_manager.sys", type("S", (), {"platform": "linux"})()
    )
    try:
        em.init_word()
        raise AssertionError("应抛 RuntimeError")
    except RuntimeError as e:
        assert "Windows" in str(e)


def test_init_excel_raises_on_non_windows(monkeypatch):
    """非 win32 平台 init_excel → RuntimeError。覆盖行 282。"""
    em = EngineManager()
    monkeypatch.setattr(
        "file_toolbox.core.batch_pdf.engine_manager.sys", type("S", (), {"platform": "linux"})()
    )
    try:
        em.init_excel()
        raise AssertionError()
    except RuntimeError:
        pass


def test_init_ppt_raises_on_non_windows(monkeypatch):
    """非 win32 平台 init_ppt → RuntimeError。覆盖行 286。"""
    em = EngineManager()
    monkeypatch.setattr(
        "file_toolbox.core.batch_pdf.engine_manager.sys", type("S", (), {"platform": "linux"})()
    )
    try:
        em.init_ppt()
        raise AssertionError()
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# COM 真路径(mock Dispatch):_init_office_app 缓存/切换/失败、_try_detect、close。
# 本机 Windows(pywin32 已装)与 CI Windows runner 上 import win32com.client 成功,
# Dispatch 被 monkeypatch 替换为 mock,不触发真实 Office。
# ---------------------------------------------------------------------------


def _stub_dispatch(monkeypatch, *, return_value=None, side_effect=None):
    """替换 win32com.client.Dispatch,返回 mock 便于断言调用次数与参数。"""
    import win32com.client

    dispatch = MagicMock()
    if side_effect is not None:
        dispatch.side_effect = side_effect
    elif return_value is not None:
        dispatch.return_value = return_value
    monkeypatch.setattr(win32com.client, "Dispatch", dispatch)
    return dispatch


def test_init_office_app_success_and_cache(monkeypatch):
    """_init_office_app 首次 Dispatch 成功 → 缓存实例;同引擎再调 → 复用,不重复 Dispatch。

    覆盖 engine_manager.py 行 246-247(缓存复用分支)。
    """
    em = EngineManager()
    app = MagicMock()
    dispatch = _stub_dispatch(monkeypatch, return_value=app)

    # 首次初始化 word(auto 引擎,且 _detect 默认返回 office 可用 → ms_prog_id)
    EngineManager._cached_engines = {"office": True, "wps": True}
    first = em.init_word()
    assert first is app
    assert dispatch.call_count == 1

    # 同引擎再调:缓存命中,不重复 Dispatch
    second = em.init_word()
    assert second is app
    assert dispatch.call_count == 1  # 仍是 1
    EngineManager._cached_engines = None


def test_init_office_app_engine_switch_quits_old(monkeypatch):
    """引擎切换(已有实例 + 引擎变了)→ 旧实例 Quit 被调用,再 Dispatch 新的。

    覆盖 engine_manager.py 行 250-254(释放旧实例)。
    """
    em = EngineManager()
    old_app = MagicMock()
    new_app = MagicMock()
    # 第一次 Dispatch 返回 old_app,第二次返回 new_app
    dispatch = _stub_dispatch(monkeypatch, side_effect=[old_app, new_app])

    EngineManager._cached_engines = {"office": True, "wps": True}
    em.init_word(engine="office")  # ms_prog_id → Word.Application
    assert dispatch.call_count == 1

    # 切换到 wps 引擎 → 旧 app.Quit 被调,再 Dispatch wps_prog_id
    em.init_word(engine="wps")
    old_app.Quit.assert_called_once()
    assert dispatch.call_count == 2
    EngineManager._cached_engines = None


def test_init_office_app_all_progid_fail_raises(monkeypatch):
    """所有 ProgID 都 Dispatch 失败 → RuntimeError(含 last_error)。

    覆盖 engine_manager.py 行 259-274(回退循环 + raise)。
    """
    em = EngineManager()
    _stub_dispatch(monkeypatch, side_effect=RuntimeError("no office"))

    EngineManager._cached_engines = {"office": True, "wps": True}
    try:
        em.init_word()
        raise AssertionError("应抛 RuntimeError")
    except RuntimeError as e:
        assert "无法启动" in str(e) or "Word" in str(e)
    EngineManager._cached_engines = None


def test_init_office_app_falls_back_to_wps(monkeypatch):
    """ms_prog_id 失败 → 回退到 wps_prog_id 并成功。

    覆盖 engine_manager.py 行 259-269(ProgID 回退顺序)。
    """
    em = EngineManager()
    wps_app = MagicMock()
    # 第一个 ProgID(ms)失败,第二个(wps)成功
    dispatch = _stub_dispatch(monkeypatch, side_effect=[RuntimeError("ms fail"), wps_app])

    EngineManager._cached_engines = {"office": True, "wps": True}
    result = em.init_word()
    assert result is wps_app
    assert dispatch.call_count == 2
    EngineManager._cached_engines = None


def test_try_detect_success_returns_true_and_quits(monkeypatch):
    """_try_detect:Dispatch 成功 → True 且 app.Quit 被调(即便 Quit 失败也不影响 True)。

    覆盖 engine_manager.py 行 79-89(成功路径)。
    """
    app = MagicMock()
    _stub_dispatch(monkeypatch, return_value=app)

    logs: list[str] = []
    assert EngineManager._try_detect("Word.Application", lambda m: logs.append(m)) is True
    app.Quit.assert_called_once()
    assert logs == []  # 成功不记日志


def test_try_detect_failure_returns_false_and_logs(monkeypatch):
    """_try_detect:Dispatch 抛异常 → False 且 log 被调用。

    覆盖 engine_manager.py 行 84-86(失败路径)。
    """
    _stub_dispatch(monkeypatch, side_effect=RuntimeError("no office"))

    logs: list[str] = []
    assert EngineManager._try_detect("Word.Application", lambda m: logs.append(m)) is False
    assert len(logs) == 1
    assert "no office" in logs[0]


def test_try_detect_quit_failure_still_returns_true(monkeypatch):
    """_try_detect:Dispatch 成功但 Quit 抛异常 → 仍返回 True(suppress 不影响判定)。

    覆盖 engine_manager.py 行 81-82(with suppress)。
    """
    app = MagicMock()
    app.Quit.side_effect = RuntimeError("quit failed")
    _stub_dispatch(monkeypatch, return_value=app)

    assert EngineManager._try_detect("Word.Application", lambda m: None) is True


def test_close_quits_apps_and_clears(monkeypatch):
    """close:有 app 时调 Quit、置 None;_from_del=False 时执行 gc.collect。

    覆盖 engine_manager.py 行 297-311。
    """
    em = EngineManager()
    word_app = MagicMock()
    excel_app = MagicMock()
    em._word_app = word_app
    em._excel_app = excel_app
    em._current_word_engine = "Word.Application"
    em._current_excel_engine = "Excel.Application"

    em.close(_from_del=False)
    word_app.Quit.assert_called_once()
    excel_app.Quit.assert_called_once()
    assert em._word_app is None
    assert em._excel_app is None
    assert em._current_word_engine is None


def test_close_skips_gc_when_from_del(monkeypatch):
    """close(_from_del=True):跳过 gc.collect(__del__ 链中不再触发,防堆损坏)。

    覆盖 engine_manager.py 行 309(if not _from_del 分支的 False 侧)。
    """
    import gc

    em = EngineManager()
    gc_collect = MagicMock()
    monkeypatch.setattr(gc, "collect", gc_collect)

    em.close(_from_del=True)
    gc_collect.assert_not_called()


def test_close_with_no_apps_does_nothing(monkeypatch):
    """close:无任何 app 时正常返回,不报错。"""
    em = EngineManager()
    em.close()  # 无 app,不抛异常即通过


def test_detect_engines_async_starts_thread_and_invokes_callback(monkeypatch):
    """detect_engines_async 启动 daemon 线程,最终调 callback(行 175-178)。

    替换 _run_async_detect 让其直接同步调 callback,验证线程被启动且 callback 触发。
    """
    em = EngineManager()
    captured = {}

    def fake_run(self, callback=None):
        # 模拟异步检测完成
        if callback:
            callback("Word.Application")

    monkeypatch.setattr(EngineManager, "_run_async_detect", fake_run)
    em.detect_engines_async(callback=lambda info: captured.setdefault("info", info))

    # 给线程一点时间执行
    time.sleep(0.2)
    assert captured.get("info") == "Word.Application"


# ---------------------------------------------------------------------------
# close:app.Quit 抛异常(行 302-303)
# ---------------------------------------------------------------------------


def test_close_quit_exception_logged(monkeypatch):
    """close 时 app.Quit 抛异常 → except 记日志,不中断(行 300-305)。"""
    em = EngineManager()
    bad_app = MagicMock()
    bad_app.Quit.side_effect = RuntimeError("quit boom")
    em._word_app = bad_app
    em._current_word_engine = "Word.Application"

    # 不应抛异常
    em.close(_from_del=True)  # from_del 跳过 gc

    # app 被置 None(即使 Quit 失败)
    assert em._word_app is None
    assert em._current_word_engine is None


def test_close_all_apps_quit_exception_continues(monkeypatch):
    """多个 app,某个 Quit 抛异常 → 继续关闭其余(行 300-305)。"""
    em = EngineManager()
    bad_word = MagicMock()
    bad_word.Quit.side_effect = RuntimeError("word quit boom")
    good_excel = MagicMock()
    em._word_app = bad_word
    em._excel_app = good_excel
    em._current_word_engine = "Word.Application"
    em._current_excel_engine = "Excel.Application"

    em.close(_from_del=True)

    # 两个 Quit 都被调用(异常不中断循环)
    bad_word.Quit.assert_called_once()
    good_excel.Quit.assert_called_once()
    assert em._word_app is None
    assert em._excel_app is None
