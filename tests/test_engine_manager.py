"""EngineManager 注册表探测/证据喂养/single-flight 单元测试。

不触发真实 COM Dispatch,仅用 monkeypatch 替换 winreg/Dispatch/engine_cache。
winreg 相关用例直接用真实模块对象做 monkeypatch,故仅在 Windows(winreg 存在)
上有效;非 Windows 跳过(产品本身的 _probe_registry 已对 ImportError 做了回退
处理)。
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.batch_pdf import engine_cache
from file_toolbox.core.batch_pdf.engine_manager import EngineManager


@pytest.fixture(autouse=True)
def _reset_engine_manager_class_state():
    """每用例前后重置 EngineManager 类级状态(缓存/缓存来源/飞行订阅者)。

    memo 与 single-flight 订阅者是类级共享状态,任一用例遗留都会改变后续用例的
    探测/投递路径;原先各用例手写的尾部清理只覆盖 _cached_engines 一项。
    """
    EngineManager._cached_engines = None
    EngineManager._cache_source = None
    EngineManager._flight_subscribers = None
    yield
    EngineManager._cached_engines = None
    EngineManager._cache_source = None
    EngineManager._flight_subscribers = None


@pytest.fixture
def engine_cache_stub(monkeypatch):
    """隔离持久引擎缓存:load/load_with_reason 可编程返回,save 只记录不落盘。

    没有此 stub 时证据喂养与缓存来源回显会真读写 cwd 下
    .file_toolbox/settings.json(含事务锁 sidecar 文件),既污染仓库工作树,
    也让断言依赖文件系统。
    """
    state = {"load": None, "reason": "missing", "saved": []}
    monkeypatch.setattr(engine_cache, "load", lambda *a, **k: state["load"])
    monkeypatch.setattr(
        engine_cache, "load_with_reason", lambda *a, **k: (state["load"], state["reason"])
    )
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
# 转换期证据喂养(record_engine_evidence):预检兑现(ensure_verified)已删除,
# 真实 Dispatch 成功即证据,精确更新缓存;临时失败不写死 False、不落盘。
# ---------------------------------------------------------------------------


def test_conversion_success_feeds_engine_evidence(monkeypatch, engine_cache_stub):
    """转换成功即喂养:Dispatch Word.Application 成功 → office=True 精确落盘。

    落盘记录的另一键保留既有持久值(wps=False),不被注册表预筛值(wps=True)
    覆盖——证据只精确更新对应引擎键,不污染整份缓存。
    """
    EngineManager._cached_engines = None
    # 注册表预筛:office 未注册、wps 注册(record_engine_evidence 补筛会用到)
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: prog_id == "KWPS.Application"
    )
    engine_cache_stub["load"] = {"office": False, "wps": False}  # 既有持久记录
    em = EngineManager()

    app = MagicMock()
    dispatch = _stub_dispatch(monkeypatch, return_value=app)

    # auto 引擎:预筛 wps-only → 目标 KWPS,但回退顺序首个 Word.Application 成功
    assert em.init_word() is app

    assert EngineManager._cached_engines["office"] is True
    assert engine_cache_stub["saved"] == [{"office": True, "wps": False}]
    assert dispatch.call_count == 1


def test_conversion_evidence_other_key_falls_back_to_cache(monkeypatch, engine_cache_stub):
    """无既有持久记录时,落盘另一键取当前进程内缓存(注册表预筛)值。"""
    EngineManager._cached_engines = None
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: prog_id == "KWPS.Application"
    )
    em = EngineManager()
    _stub_dispatch(monkeypatch, return_value=MagicMock())

    assert em.init_word() is not None

    # 预筛 {office:False,wps:True} + office 证据 → {office:True,wps:True}
    assert engine_cache_stub["saved"] == [{"office": True, "wps": True}]


def test_transient_dispatch_failure_keeps_registry_verdict(monkeypatch, engine_cache_stub):
    """临时 Dispatch 失败不得写死 False:registry office=True + 首个 ProgID 失败 →
    缓存 office 保持 True、save 未以 office=False 落盘、回退循环仍尝试第二 ProgID。

    旧实现(ensure_verified 把临时 Dispatch 失败写成 False 并落盘 7 天)此测试必红。
    """
    EngineManager._cached_engines = {"office": True, "wps": True}
    em = EngineManager()

    wps_app = MagicMock()
    dispatch = _stub_dispatch(monkeypatch, side_effect=[RuntimeError("office busy"), wps_app])

    assert em.init_word() is wps_app  # 首个 ProgID(Word)失败 → 回退 KWPS 成功
    assert dispatch.call_count == 2

    # office 键保持注册表结论 True;落盘记录里 office 恒为 True(只追加 wps 证据)
    assert EngineManager._cached_engines["office"] is True
    assert engine_cache_stub["saved"] == [{"office": True, "wps": True}]


def test_record_engine_evidence_false_is_warning_only(engine_cache_stub, caplog):
    """record_engine_evidence(engine, False):不改缓存、不落盘,只记 warning。"""
    EngineManager._cached_engines = {"office": True, "wps": False}
    em = EngineManager()

    with caplog.at_level("WARNING"):
        em.record_engine_evidence("office", False)

    assert EngineManager._cached_engines == {"office": True, "wps": False}  # 不改缓存
    assert engine_cache_stub["saved"] == []  # 不落盘
    assert any("office" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# 检测终态契约、缓存来源回显(AC2)、single-flight 并发合并(AC5)、memo 快速路径
# ---------------------------------------------------------------------------


def test_detect_persists_no_engine_conclusion(monkeypatch, engine_cache_stub):
    """注册表判定双无 → 检测完成落盘 {False,False}(AC2:无 Office 也有可缓存结论)。"""
    EngineManager._cached_engines = None
    em = EngineManager()
    monkeypatch.setattr(EngineManager, "_probe_registry", lambda prog_id: False)

    received: list[str] = []
    em._async_detect_body(callback=received.append)

    assert engine_cache_stub["saved"] == [{"office": False, "wps": False}]
    assert received == ["未检测到Office软件"]  # missing 来源 → 无后缀


def test_engine_info_appends_suffix_on_cache_hit(monkeypatch, engine_cache_stub):
    """持久记录与检测结果一致(hit)→ 文案含"（缓存已验证）"后缀。"""
    EngineManager._cached_engines = None
    em = EngineManager()
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: prog_id == "Word.Application"
    )
    engine_cache_stub["load"] = {"office": True, "wps": False}
    engine_cache_stub["reason"] = "hit"

    received: list[str] = []
    em._async_detect_body(callback=received.append)

    assert "MS Office" in received[0]
    assert "（缓存已验证）" in received[0]


def test_engine_info_no_suffix_on_mismatch_or_missing(monkeypatch, engine_cache_stub):
    """持久记录缺失(missing)或与检测结果不一致(mismatch)→ 文案无后缀。"""
    EngineManager._cached_engines = None
    em = EngineManager()
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: prog_id == "Word.Application"
    )

    received: list[str] = []
    em._async_detect_body(callback=received.append)
    assert "（缓存已验证）" not in received[0]  # missing

    # mismatch:有有效持久记录,但与本次注册表检测结果不一致(安装发生变化)
    EngineManager._cached_engines = None
    engine_cache_stub["load"] = {"office": False, "wps": False}
    engine_cache_stub["reason"] = "hit"
    received.clear()
    em._async_detect_body(callback=received.append)
    assert "（缓存已验证）" not in received[0]


def test_async_detect_body_reports_failure_as_terminal_state(monkeypatch):
    """探测抛异常 → callback 恰好收到一次"引擎检测失败: ..."终态文案。

    旧实现 except 只记 warning 不回调(页面停在"正在检测"收不到终态),此测试必红。
    """

    def raise_boom(**kwargs):
        raise RuntimeError("boom")

    em = EngineManager()
    monkeypatch.setattr(em, "_detect_available_engines", raise_boom)

    received: list[str] = []
    result = em._async_detect_body(callback=received.append)

    assert received == ["引擎检测失败: boom"]
    assert result == "引擎检测失败: boom"


def test_detect_engines_async_single_flight_merges_concurrent_requests(
    monkeypatch, engine_cache_stub
):
    """single-flight:并发两次 detect_engines_async 只探测一次,两订阅者同获结果。

    旧实现(每请求各开 daemon 线程、各自探测)此测试必红:探测会发生两次。
    回调在锁外执行:回调内能立即获取飞行锁即证明投递未持锁(GUI 不等锁)。
    """
    EngineManager._cached_engines = None
    probe_started = threading.Event()
    release_probe = threading.Event()
    probe_calls: list[bool] = []

    def blocking_detect(self, force_refresh=False):
        probe_calls.append(force_refresh)
        probe_started.set()
        assert release_probe.wait(timeout=5), "探测阻塞超过 5s,测试自身失败"
        return {"office": True, "wps": False}

    monkeypatch.setattr(EngineManager, "_detect_available_engines", blocking_detect)

    lock_free_during_callback: list[bool] = []
    results: list[str] = []

    def subscriber(info: str) -> None:
        # 回调在锁外:能立即拿到飞行锁说明投递时未持锁
        if EngineManager._flight_lock.acquire(timeout=2):
            EngineManager._flight_lock.release()
            lock_free_during_callback.append(True)
        results.append(info)

    em = EngineManager()
    em.detect_engines_async(callback=subscriber)
    assert probe_started.wait(timeout=5)  # 首个 flight 的探测已进入阻塞点
    em.detect_engines_async(callback=subscriber)  # 并发第二订阅 → 合并进同一 flight

    release_probe.set()

    deadline = time.time() + 5
    while len(results) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert probe_calls == [False]  # 恰好一次探测,且为注册表路径(force_refresh=False)
    assert len(results) == 2 and results[0] is results[1]  # 同一结果对象广播
    assert lock_free_during_callback == [True, True]


def test_serve_flight_isolates_failing_subscriber(monkeypatch):
    """_serve_flight:结果广播在锁外;单个订阅者抛异常不影响其余订阅者收到结果。"""
    em = EngineManager()
    monkeypatch.setattr(EngineManager, "_async_detect_body", lambda self, callback=None: "探测文案")

    def bad_subscriber(info: str) -> None:
        raise RuntimeError("subscriber boom")

    received: list[str] = []
    with EngineManager._flight_lock:
        EngineManager._flight_subscribers = [bad_subscriber, received.append]

    em._serve_flight()

    assert received == ["探测文案"]
    assert EngineManager._flight_subscribers is None  # 飞行已解除


def test_async_detect_body_memo_fast_path(monkeypatch, engine_cache_stub):
    """memo 快速路径:_cached_engines 已填充 → 再次检测直接返回,不重复探测注册表。"""
    EngineManager._cached_engines = None
    em = EngineManager()
    probed: list[str] = []
    monkeypatch.setattr(
        EngineManager, "_probe_registry", lambda prog_id: probed.append(prog_id) or True
    )

    em._async_detect_body()
    assert len(probed) == 2  # 首次探测 Word + KWPS
    em._async_detect_body()
    assert len(probed) == 2  # memo 命中,未重探注册表


def test_async_detect_body_uses_registry_probe_not_dispatch(monkeypatch, engine_cache_stub):
    """回归:启动异步检测必须走注册表(force_refresh=False),不应触发真 Dispatch。

    此前 detect_engines_async 的 worker 以 force_refresh=True 调用,每次打开对话框都
    Dispatch Word/WPS,违背注册表快速探测的设计目标。worker 体已抽到
    _async_detect_body,可直接同步断言。
    适配说明(Issue #123):检测体新增缓存来源回显,故补 engine_cache_stub 隔离
    持久缓存读写。
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


def test_init_office_app_success_and_cache(monkeypatch, engine_cache_stub):
    """_init_office_app 首次 Dispatch 成功 → 缓存实例;同引擎再调 → 复用,不重复 Dispatch。

    覆盖 engine_manager.py 行 246-247(缓存复用分支)。
    适配说明(Issue #123):成功路径新增证据喂养(engine_cache_stub 隔离落盘)。
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


def test_init_office_app_engine_switch_quits_old(monkeypatch, engine_cache_stub):
    """引擎切换(已有实例 + 引擎变了)→ 旧实例 Quit 被调用,再 Dispatch 新的。

    覆盖 engine_manager.py 行 250-254(释放旧实例)。
    适配说明(Issue #123):成功路径新增证据喂养(engine_cache_stub 隔离落盘)。
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


def test_init_office_app_falls_back_to_wps(monkeypatch, engine_cache_stub):
    """ms_prog_id 失败 → 回退到 wps_prog_id 并成功。

    覆盖 engine_manager.py 行 259-269(ProgID 回退顺序)。
    适配说明(Issue #123):成功路径新增证据喂养(engine_cache_stub 隔离落盘)。
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
    """detect_engines_async 启动 daemon 线程,经 single-flight 投递调 callback。

    适配说明(Issue #123):投递改由 _serve_flight 负责,_run_async_detect 不再
    逐请求携带 callback,故改为 mock 可测核心体 _async_detect_body(真实线程 +
    真实投递路径)。
    """
    em = EngineManager()
    captured = {}

    monkeypatch.setattr(
        EngineManager, "_async_detect_body", lambda self, callback=None: "Word.Application"
    )
    em.detect_engines_async(callback=lambda info: captured.setdefault("info", info))

    deadline = time.time() + 5
    while "info" not in captured and time.time() < deadline:
        time.sleep(0.01)
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
