"""
Office引擎管理器

负责检测和初始化 Microsoft Office / WPS Office 应用。

检测/验证模型(Issue #123 后的语义):
- 启动期检测走注册表探测(毫秒级,不启动 Office 进程),并发请求由 single-flight
  合并为一次探测。
- 不存在独立的"预检兑现"步骤:真实 COM Dispatch 的成功本身就是最强证据,由
  `_init_office_app` 在转换期成功后经 `record_engine_evidence` 喂养缓存(精确
  更新对应引擎键);临时 Dispatch 失败不写缓存、不落盘,由 `_prog_ids_to_try`
  的转换期 ProgID 回退兜底。
"""

import contextlib
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.office_session import ComSession, dispose_office_app, init_office_app
from file_toolbox.common.paths import DataRootPolicy, current_data_root_policy, use_data_root_policy

from . import engine_cache
from .constants import ENGINE_AUTO, ENGINE_WPS


@dataclass(frozen=True)
class _AppSpec:
    """单个 Office 应用的配置(app 实例属性、引擎属性、各引擎 ProgID、检测用 ProgID)。"""

    kind: str  # word | excel | ppt
    app_attr: str  # self._word_app 等
    engine_attr: str  # self._current_word_engine 等
    ms_prog_id: str  # Microsoft Office ProgID
    wps_prog_id: str  # WPS Office ProgID
    label: str  # 错误提示用名


# 三种应用的配置表 —— 新增应用只需在此添加一行。
_APP_CONFIG: dict[str, _AppSpec] = {
    "word": _AppSpec(
        "word", "_word_app", "_current_word_engine", "Word.Application", "KWPS.Application", "Word"
    ),
    "excel": _AppSpec(
        "excel",
        "_excel_app",
        "_current_excel_engine",
        "Excel.Application",
        "Ket.Application",
        "Excel",
    ),
    "ppt": _AppSpec(
        "ppt",
        "_ppt_app",
        "_current_ppt_engine",
        "PowerPoint.Application",
        "KWPP.Application",
        "PowerPoint",
    ),
}


def _engine_suite_for_prog_id(prog_id: str) -> str | None:
    """按 ProgID 反查所属引擎套件:任一 kind 的 ms_prog_id → "office",
    wps_prog_id → "wps";不在配置表内 → None(调用方据此跳过证据喂养)。"""
    for spec in _APP_CONFIG.values():
        if prog_id == spec.ms_prog_id:
            return "office"
        if prog_id == spec.wps_prog_id:
            return "wps"
    return None


class ProbeState(StrEnum):
    """外部能力预筛的三态结论(Office kind 与包内 Pandoc 共用)。

    AVAILABLE/MISSING 是可展示的确定结论(探测可判定);PROBE_ERROR 表示
    探测本身失败(如权限 OSError),不得当作"未安装"展示。
    """

    AVAILABLE = "available"
    MISSING = "missing"
    PROBE_ERROR = "probe_error"


@dataclass(frozen=True)
class KindAvailability:
    """单 kind 的按需可用性(注册表预筛结论 + 进程内真实 Dispatch 证据)。

    state=AVAILABLE 时 engine 指向命中的套件(优先 MS Office);verified=True
    仅表示本进程真实 Dispatch 成功过(最强证据),预筛命中不能冒称真实转换
    验证;detail 携带检测错误原因或平台说明,供页面准确展示。
    """

    kind: str
    state: ProbeState
    engine: str | None = None
    detail: str = ""
    verified: bool = False


@dataclass(frozen=True)
class _ProbeOutcome:
    """单 ProgID 注册表探测结果:registered=None 表示探测失败(无法判定)。

    FileNotFoundError → registered=False(确定未注册);OSError → None(检测
    错误,与"未安装"严格区分);非 Windows(winreg 不可用)→ False 附平台说明。
    """

    registered: bool | None
    detail: str = ""


@dataclass(frozen=True)
class _KindProbes:
    """单 kind 的两套件探测原始结果(按 kind memo 的存储形态)。

    MS 与 WPS 的结论都保留(P4):MS 探测错误不再提前终止——支持 WPS 的
    消费者在 WPS 注册命中时仍可得出可用,仅 MS 消费者保留原 MS 错误;选择
    逻辑见 EngineManager._select_availability。
    """

    ms: _ProbeOutcome
    wps: _ProbeOutcome

    def outcome(self, engine: str) -> _ProbeOutcome:
        return self.ms if engine == "office" else self.wps


# 套件键与固定优先顺序(MS 优先;engines=None 视为全支持)
_SUITES = ("office", "wps")


def _probe_registry_outcome(prog_id: str) -> _ProbeOutcome:
    """注册表探测的完整三态结果(供按 kind 能力查询区分缺失/检测错误)。"""
    try:
        import winreg
    except ImportError:
        return _ProbeOutcome(False, "此功能仅支持 Windows 系统")  # 非 Windows
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
    except FileNotFoundError:
        return _ProbeOutcome(False, "")
    except OSError as error:
        return _ProbeOutcome(None, str(error))
    winreg.CloseKey(key)
    return _ProbeOutcome(True, "")


class EngineManager(LoggableMixin):
    """Office引擎管理器"""

    # 检测结果缓存（类变量，所有实例共享）：None = 尚未检测过。
    _cached_engines: dict[str, bool] | None = None
    # 最近一次检测完成后持久缓存的状态("hit"/"mismatch"/"expired"/"future"/
    # "invalid"/"missing"/"io");None = 本进程尚未完成过检测,get_engine_info
    # 不加缓存来源后缀。
    _cache_source: str | None = None
    # single-flight 并发合并(AC5):类级锁保护订阅者列表;列表非 None 表示有
    # 进行中的探测 flight,并发 detect_engines_async 挂入列表而非各开线程。
    # 锁内只做登记,回调投递一律在锁外(见 _serve_flight)。
    _flight_lock = threading.Lock()
    _flight_subscribers: list[Callable[[str], None]] | None = None
    # 按 kind 的能力预筛 memo(类变量,所有实例共享):None = 尚未查询过。
    # 与套件级 _cached_engines 互补:套件缓存以 Word/KWPS ProgID 判定 office/wps
    # 套件,不能据此推断 Excel/PPT 的存在;按 kind 查询各自探测其两套件 ProgID,
    # 仅进程内 memo、不落盘(持久缓存仍由 engine_cache 承担)。memo 存无约束的
    # 原始双套件探测结果(_KindProbes),engines 约束在选择时应用,同一 kind 的
    # 不同工具查询互不污染。
    _cached_kind_probes: dict[str, _KindProbes] | None = None
    # 本进程经真实 Dispatch 成功过的 kind → 实际成功的套件(office/wps);
    # 转换期喂养,最强证据:绑定实际套件并可纠正旧预筛(含 missing/probe_error)。
    _verified_kinds: dict[str, str] = {}

    def __init__(self) -> None:
        self._word_app = None
        self._excel_app = None
        self._ppt_app = None
        self._current_word_engine: str | None = None
        self._current_excel_engine: str | None = None
        self._current_ppt_engine: str | None = None
        self._office_thread: int | None = None
        self._office_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  引擎检测
    # ------------------------------------------------------------------ #
    @staticmethod
    def _try_detect(prog_id: str, log: Callable[[str], None]) -> bool:
        """尝试 Dispatch 一个 ProgID,成功即视为引擎可用。"""
        try:
            with ComSession():
                app = init_office_app(prog_id)
                try:
                    return True
                finally:
                    dispose_office_app(app, prog_id)
                    app = None
        except Exception as error:
            log(str(error))
            return False

    @staticmethod
    def _probe_registry(prog_id: str) -> bool:
        """注册表探测(bool 视图,兼容既有消费者):HKCR 下是否存在该 ProgID。

        作为快速预筛——"注册了"基本等于"装了";更强证据由转换期真实 Dispatch
        成功后喂养(record_engine_evidence)。非 Windows 或 winreg 不可用时返回
        False;探测本身的 OSError 也返回 False(需要区分"缺失/检测错误"的调用
        方改用 _probe_registry_outcome / kind_availability)。
        """
        return _probe_registry_outcome(prog_id).registered is True

    def _detect_available_engines(self, force_refresh: bool = False) -> dict[str, bool]:
        """检测可用的 Office 引擎(带缓存)。

        - 默认(force_refresh=False):走注册表探测,毫秒级,不启动 Office 进程;
          进程内 memo(``_cached_engines`` 已填充)时直接返回,不重复探测。
        - force_refresh=True:走真 Dispatch(_try_detect),用于显式重检与测试 seam。
        """
        if EngineManager._cached_engines is not None and not force_refresh:
            return EngineManager._cached_engines

        if force_refresh:
            # 真兑现:Dispatch 进程外服务器
            engines = {
                "office": self._try_detect(
                    "Word.Application",
                    lambda m: self.logger.warning(f"检测Microsoft Office Word失败: {m}"),
                ),
                "wps": self._try_detect(
                    "KWPS.Application",
                    lambda m: self.logger.warning(f"检测WPS Office失败: {m}"),
                ),
            }
        else:
            # 快速预筛:注册表(经类访问 staticmethod,保持静态语义)
            engines = {
                "office": EngineManager._probe_registry("Word.Application"),
                "wps": EngineManager._probe_registry("KWPS.Application"),
            }

        EngineManager._cached_engines = engines
        return engines

    @classmethod
    def _mark_kind_verified(cls, kind: str, engine: str) -> None:
        """真实 Dispatch 成功后记录 kind 与实际成功的套件(进程内证据,不落盘)。

        证据绑定实际套件:MS 预筛命中但 Dispatch 回退 WPS 成功时,以 WPS 为准;
        预筛 missing/probe_error 被真实成功纠正。与套件级 record_engine_evidence
        互补(套件键持久化,kind 证据只影响本进程能力展示,不另建持久缓存)。
        """
        cls._verified_kinds[kind] = engine

    @classmethod
    def record_kind_success(cls, kind: str, engine: str = "office") -> None:
        """登记一次非 PDF 适配器的真实 Office COM 会话成功(能力层入口)。

        考勤等直接经 common.office_session 建 COM 会话的适配器在 Dispatch
        成功后调用;与转换期 _mark_kind_verified 同一进程内证据存储(不落盘、
        不新建缓存/回调框架)。kind 必须是 _APP_CONFIG 登记类别,engine 限
        office/wps——成功的 Dispatch 是最强证据,可纠正旧预筛(含 probe_error)。

        线程/IO 契约:classmethod 纯字典登记,不实例化 EngineManager、不
        读写 engine_cache/settings(考勤等后台 worker 线程可直接调用,不涉及
        数据根 policy 传播)。
        """
        if kind not in _APP_CONFIG:
            raise ValueError(f"未知的 Office 应用类别: {kind!r}")
        if engine not in _SUITES:
            raise ValueError(f"未知的引擎套件: {engine!r}")
        cls._mark_kind_verified(kind, engine)

    def _select_availability(
        self, kind: str, probes: _KindProbes, engines: tuple[str, ...] | None
    ) -> KindAvailability:
        """在支持套件约束内从双套件探测结果选择实际可用性(P4/F7 合并语义)。

        规则(复用同一份按 kind memo 与 verified 证据,不另建缓存;
        engines=None 视为两套件全支持):
        1. verified 证据绑定的实际成功套件在集合内 → AVAILABLE+verified(实际
           成功优先,不因约束丢失"实际套件"语义);
        2. 集合内注册命中(MS 优先)→ AVAILABLE;同集合内另一套件探测失败时
           详情保留该错误(不因回退命中丢弃);
        3. 集合内无命中但有探测失败 → PROBE_ERROR(保留原错误,不冒称缺失,
           也不把集合外命中丢成错误状态);
        4. 集合内全部确定未注册而集合外有命中 → MISSING,engine 保留检测到的
           套件名供展示层说明"检测到但该工具不支持";
        5. 全部确定未注册 → MISSING。
        """
        allowed = (
            _SUITES if engines is None else tuple(suite for suite in _SUITES if suite in engines)
        )
        verified = EngineManager._verified_kinds.get(kind)
        if verified is not None and verified in allowed:
            return KindAvailability(kind, ProbeState.AVAILABLE, verified, "", True)
        for suite in allowed:
            if probes.outcome(suite).registered is True:
                detail = ""
                for other in allowed:
                    if other != suite and probes.outcome(other).registered is None:
                        detail = probes.outcome(other).detail
                return KindAvailability(kind, ProbeState.AVAILABLE, suite, detail)
        for suite in allowed:
            outcome = probes.outcome(suite)
            if outcome.registered is None:
                return KindAvailability(kind, ProbeState.PROBE_ERROR, detail=outcome.detail)
        for suite in _SUITES:
            if suite not in allowed and probes.outcome(suite).registered is True:
                return KindAvailability(kind, ProbeState.MISSING, suite)
        return KindAvailability(
            kind, ProbeState.MISSING, detail=probes.ms.detail or probes.wps.detail
        )

    def kind_availability(
        self, kind: str, *, refresh: bool = False, engines: tuple[str, ...] | None = None
    ) -> KindAvailability:
        """查询单 kind(word/excel/ppt)的按需可用性(注册表预筛,毫秒级)。

        - 不启动任何 Office 进程;结果进程内 memo(refresh=True 强制重探)。
        - 各 kind 独立探测自己的 ms/wps ProgID:Word 缺失不能否定 Excel/PPT,
        - 探测 OSError 与"未注册"严格区分(PROBE_ERROR ≠ MISSING)。
        - MS 探测错误不提前终止(P4):两套件结论都入 memo——支持 WPS 的调用
          方在 WPS 注册命中时如实可用(错误保留在详情),仅 MS 的调用方保留
          原 MS 探测错误,不把 WPS 成功或原错误丢成错误状态。
        - verified 由真实 Dispatch 成功喂养(见 _init_office_app_locked /
          record_kind_success),注册存在仅是预筛,不是真实转换验证。
        - engines(可选):调用工具的适配器实际支持的套件集合。提供时在集合
          内选择实际可用性(见 _select_availability)。
        """
        if kind not in _APP_CONFIG:
            raise ValueError(f"未知的 Office 应用类别: {kind!r}")
        if not refresh:
            cached = EngineManager._cached_kind_probes
            if cached is not None and (hit := cached.get(kind)) is not None:
                return self._select_availability(kind, hit, engines)
        spec = _APP_CONFIG[kind]
        probes = _KindProbes(
            ms=_probe_registry_outcome(spec.ms_prog_id),
            wps=_probe_registry_outcome(spec.wps_prog_id),
        )
        memo = EngineManager._cached_kind_probes or {}
        memo[kind] = probes
        EngineManager._cached_kind_probes = memo
        return self._select_availability(kind, probes, engines)

    def record_engine_evidence(self, engine: str, available: bool) -> None:
        """记录一条来自真实转换的引擎证据,精确更新进程内缓存与持久缓存。

        本方法由"保证不抛出"的路径调用(证据是转换的副产品,不是门槛),写失败
        仅告警。

        - ``available=True``:真实 Dispatch 转换成功,优先于注册表预筛结论——
          ``_cached_engines[engine] = True``;持久化精确更新该键:落盘记录中本键
          =True,另一键优先取现有有效持久记录值,否则取当前进程内缓存值,不污染
          整份缓存。
        - ``available=False``:临时失败(Office 忙/会话损坏)与"未安装"不可区分,
          只记 warning——不改 ``_cached_engines``、不落盘,临时失败不得固化为
          TTL 级结论;兜底由 ``_prog_ids_to_try`` 转换期逐 ProgID 回退承担。
        - ``_cached_engines`` 为 None(未经检测直接转换)时先补注册表预筛(毫秒级)。
        """
        if not available:
            self.logger.warning(f"引擎证据: {engine} 本轮转换失败(临时性,不写入缓存)")
            return

        if EngineManager._cached_engines is None:
            self._detect_available_engines()  # 注册表预筛(毫秒级)
        cached = EngineManager._cached_engines or {}
        cached[engine] = True
        EngineManager._cached_engines = cached

        persisted, _reason = engine_cache.load_with_reason()
        record = dict(persisted) if persisted is not None else dict(cached)
        record[engine] = True
        if engine_cache.save(record):
            self.logger.info(f"引擎证据: {engine} 可用(真实转换成功),缓存已更新")
        else:
            self.logger.warning("引擎证据缓存写入失败(不影响本次转换)")

    def _refresh_cache_source(self, engines: dict[str, bool]) -> None:
        """检测完成后刷新缓存来源回显(类属性 ``_cache_source``)并做诊断日志。

        持久记录与本次检测结果一致 → "hit"(get_engine_info 加"（缓存已验证）"
        后缀);有记录但不一致 → "mismatch";无有效记录 → 透传 load_with_reason
        的原因(missing/expired/future/invalid/io)。

        确定未安装(office=False 且 wps=False)也是可缓存结论:落盘
        ``{"office": False, "wps": False}``,让无 Office 机器的下个进程直接命中
        缓存回显(AC2),免重复探测。
        """
        persisted, reason = engine_cache.load_with_reason()
        if persisted is not None and persisted == engines:
            EngineManager._cache_source = "hit"
        elif persisted is not None:
            EngineManager._cache_source = "mismatch"
        else:
            EngineManager._cache_source = reason
        self.logger.info(f"引擎缓存: {EngineManager._cache_source}")
        if engines == {"office": False, "wps": False}:
            engine_cache.save({"office": False, "wps": False})

    def get_engine_info(self, use_cache: bool = True) -> str:
        """获取当前引擎信息。

        持久缓存命中(``_cache_source == "hit"``)时文案追加"（缓存已验证）"
        后缀,向用户回显结论的缓存来源;其余来源(含未检测过)不加后缀。
        """
        if use_cache and EngineManager._cached_engines is None:
            return "正在检测可用引擎..."

        engines = self._detect_available_engines(force_refresh=not use_cache)
        info_parts = []

        if engines["office"]:
            info_parts.append("MS Office (Microsoft Print To PDF)")
        if engines["wps"]:
            info_parts.append("WPS (Kingsoft Virtual Printer)")

        info = "未检测到Office软件" if not info_parts else "可用引擎: " + "、".join(info_parts)
        if EngineManager._cache_source == "hit":
            info += "（缓存已验证）"
        return info

    def detect_engines_async(self, callback: Callable[[str], None] | None = None) -> None:
        """异步检测引擎(single-flight 并发合并,不阻塞调用线程)。

        - 锁内只做登记:无进行中的探测 flight 时登记新 flight 并启动一个 daemon
          线程;已有 flight 时把 callback 挂入订阅者列表后立即返回——并发请求合并
          为一次探测(AC5),同一结果由 _serve_flight 在锁外广播给全部订阅者。
        - 探测走**注册表**(force_refresh=False):毫秒级、不启动任何 Office 进程;
          真实 COM Dispatch 的证据由转换期 `_init_office_app` 成功后喂养,启动期
          零 Dispatch(避免打开对话框就拉起 Word/WPS 的卡顿与进程泄漏)。
        - 飞行标志在**结果计算完成后**才清除:清除后到达的晚到订阅者会开启新
          flight,其探测体命中进程内 memo(``_cached_engines`` 已填充,不再重探
          注册表),开销可忽略——与"并入旧 flight"同为正确行为,取实现最简者。
        - 禁止在锁内执行回调、禁止让 GUI 等锁:登记临界区不含任何探测/IO。

        把检测放后台线程是为了既不冻结 GUI 主线程,也让结果异步切回对话框线程
        (pdf_tab 经 _engine_detected 信号桥投递,见其 docstring)。

        COM 注意:即便走注册表探测,探测线程也保留 CoInitialize 配对(见
        _run_async_detect),以防未来扩展为真 Dispatch;win32com 要求使用它的每个
        线程先 CoInitialize,否则进程退出时抛 CO_E_NOTINITIALIZED(0x800401f0)
        致命异常。

        数据根(F8):ContextVar 不随线程继承——探测体内的 engine_cache 读/写
        必须命中调用线程的数据根 policy,故启动线程前捕获快照并传入
        _run_async_detect 重入,否则会落到线程默认的 cwd 根(打包运行即 HOME)。
        """
        launch_flight = False
        with EngineManager._flight_lock:
            if EngineManager._flight_subscribers is None:
                EngineManager._flight_subscribers = []
                launch_flight = True
            if callback is not None:
                EngineManager._flight_subscribers.append(callback)
        if launch_flight:
            policy = current_data_root_policy()  # 调用线程捕获(GUI 线程的便携根)
            # daemon=True: 进程退出时无需等待,避免测试/关闭时悬挂
            threading.Thread(target=self._run_async_detect, args=(policy,), daemon=True).start()

    def _run_async_detect(self, data_root_policy: DataRootPolicy) -> None:
        """后台线程入口:数据根 policy 重入 + CoInitialize 配对 + single-flight 投递。"""
        session = ComSession()
        com_inited = False
        try:
            session.__enter__()
            com_inited = True
        except Exception:
            com_inited = False  # 非 Windows / 无 pywin32
        try:
            with use_data_root_policy(data_root_policy):
                self._serve_flight()
        finally:
            if com_inited:
                with contextlib.suppress(Exception):
                    session.__exit__(None, None, None)

    def _serve_flight(self) -> None:
        """single-flight 投递体:计算一次结果,广播给订阅者,再解除飞行。

        订阅者列表在**结果计算完成后**于锁内取走并清空——飞行中到达的请求并入
        本次投递;清除之后到达的请求由 detect_engines_async 开启新 flight(见其
        docstring 的晚到订阅者策略)。回调逐个在锁外执行,单个订阅者抛异常不影响
        其余订阅者收到结果。
        """
        result = self._async_detect_body()
        with EngineManager._flight_lock:
            subscribers = EngineManager._flight_subscribers or []
            EngineManager._flight_subscribers = None
        for subscriber in subscribers:
            try:
                subscriber(result)
            except Exception:
                self.logger.warning("引擎检测回调投递失败", exc_info=True)

    def _async_detect_body(self, callback: Callable[[str], None] | None = None) -> str:
        """detect_engines_async 的可测核心体(同步可调用,不依赖 COM)。

        终态契约:成功与异常都必回调一次——成功回调/返回检测完成后的展示文案
        (含缓存来源后缀,见 _refresh_cache_source);任何异常回调/返回
        ``"引擎检测失败: {e}"``,页面不会停在"正在检测"状态。callback 在 try
        之外调用:订阅者自身抛错不会被误报成检测失败,也不会触发二次回调。
        """
        try:
            engines = self._detect_available_engines()  # force_refresh=False → 注册表/memo
            self._refresh_cache_source(engines)
            result = self.get_engine_info(use_cache=True)
        except Exception as e:  # COM/线程异常不应波及调用线程
            result = f"引擎检测失败: {e}"
            self.logger.warning(f"异步引擎检测失败: {e}")
        if callback is not None:
            callback(result)
        return result

    # ------------------------------------------------------------------ #
    #  应用初始化(配置驱动)
    # ------------------------------------------------------------------ #
    def _get_prog_id(self, kind: str, engine: str = ENGINE_AUTO) -> str:
        """根据 kind 与引擎选择返回首选 ProgID(auto 时按检测结果优先 MS Office)。"""
        spec = _APP_CONFIG[kind]
        if engine == ENGINE_AUTO:
            engines = self._detect_available_engines()
            if engines["wps"] and not engines["office"]:
                return spec.wps_prog_id
            return spec.ms_prog_id
        if engine == ENGINE_WPS:
            return spec.wps_prog_id
        return spec.ms_prog_id

    def _prog_ids_to_try(self, kind: str, engine: str) -> list[str]:
        """按引擎偏好返回 ProgID 尝试顺序(含回退)。"""
        spec = _APP_CONFIG[kind]
        if engine == ENGINE_WPS:
            return [spec.wps_prog_id, spec.ms_prog_id]
        # ENGINE_AUTO / ENGINE_MS_OFFICE:均优先 MS Office
        return [spec.ms_prog_id, spec.wps_prog_id]

    def _init_office_app(self, kind: str, engine: str = ENGINE_AUTO) -> Any:
        if not self._office_lock.acquire(blocking=False):
            raise RuntimeError("Office 会话正在初始化或释放")
        try:
            return self._init_office_app_locked(kind, engine)
        finally:
            self._office_lock.release()

    def _init_office_app_locked(self, kind: str, engine: str) -> Any:
        """通用初始化逻辑,由 init_word/excel/ppt 复用。"""
        if sys.platform != "win32":
            raise RuntimeError("此功能仅支持 Windows 系统")

        if self._office_thread is not None and self._office_thread != threading.get_ident():
            raise RuntimeError("Office 会话仍属于另一线程，必须先由创建线程释放")

        spec = _APP_CONFIG[kind]
        current_app = getattr(self, spec.app_attr)
        target_prog_id = self._get_prog_id(kind, engine)

        # 已有实例且引擎未变:直接复用
        if current_app is not None and getattr(self, spec.engine_attr) == target_prog_id:
            return current_app

        # 引擎切换:先释放旧实例
        if current_app is not None:
            dispose_office_app(current_app, getattr(self, spec.engine_attr), raise_on_error=True)
            setattr(self, spec.app_attr, None)
            setattr(self, spec.engine_attr, None)

        last_error = None
        for prog_id in self._prog_ids_to_try(kind, engine):
            try:
                app = init_office_app(prog_id)
                self._office_thread = threading.get_ident()
                setattr(self, spec.app_attr, app)
                setattr(self, spec.engine_attr, prog_id)
                # 真实 Dispatch 成功是最强证据:精确喂养该引擎键(record_engine_
                # evidence 保证不抛,不会把成功转换误入下方回退分支)。Dispatch
                # 失败的分支不记录 False——临时忙与装坏不可区分,由回退循环兜底。
                suite = _engine_suite_for_prog_id(prog_id)
                if suite is not None:
                    self.record_engine_evidence(suite, True)
                    # 真实 Dispatch 成功同时是本 kind 的最强证据:绑定实际成功
                    # 的套件(回退 WPS 成功时不冒称 MS),并纠正旧预筛结论。
                    EngineManager._mark_kind_verified(kind, suite)
                return app
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"无法启动 {spec.label} 应用程序。请确保已安装 Microsoft Office 或 WPS Office。\n"
            f"详细错误: {last_error}"
        )

    def init_word(self, engine: str = ENGINE_AUTO) -> Any:
        """初始化Word应用，支持引擎切换"""
        return self._init_office_app("word", engine)

    def init_excel(self, engine: str = ENGINE_AUTO) -> Any:
        """初始化Excel应用，支持引擎切换"""
        return self._init_office_app("excel", engine)

    def init_ppt(self, engine: str = ENGINE_AUTO) -> Any:
        """初始化PowerPoint应用，支持引擎切换"""
        return self._init_office_app("ppt", engine)

    def close(self, _from_del: bool = False, *, strict: bool = False) -> None:
        """创建线程显式释放专属应用；析构不发送跨线程 COM 调用。"""
        if _from_del:
            return
        if not self._office_lock.acquire(blocking=False):
            raise RuntimeError("Office 会话正在初始化或释放")
        try:
            self._close_office_apps(strict=strict)
        finally:
            self._office_lock.release()

    def _close_office_apps(self, *, strict: bool) -> None:
        if self._office_thread is not None and self._office_thread != threading.get_ident():
            raise RuntimeError("Office 会话必须在创建线程释放")
        errors: list[Exception] = []
        for spec in _APP_CONFIG.values():
            app = getattr(self, spec.app_attr, None)
            if app is not None:
                try:
                    dispose_office_app(app, getattr(self, spec.engine_attr), raise_on_error=True)
                except Exception as error:
                    self.logger.error(f"关闭{spec.label}应用失败: {error}")
                    errors.append(error)
                finally:
                    setattr(self, spec.app_attr, None)
                    setattr(self, spec.engine_attr, None)
        self._office_thread = None
        if strict and errors:
            raise ExceptionGroup("Office 释放失败: " + "; ".join(map(str, errors)), errors)

    def __del__(self) -> None:  # pragma: no cover
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close(_from_del=True)
