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
from typing import Any

from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.common.office_session import init_office_app

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

    def __init__(self) -> None:
        self._word_app = None
        self._excel_app = None
        self._ppt_app = None
        self._current_word_engine: str | None = None
        self._current_excel_engine: str | None = None
        self._current_ppt_engine: str | None = None

    # ------------------------------------------------------------------ #
    #  引擎检测
    # ------------------------------------------------------------------ #
    @staticmethod
    def _try_detect(prog_id: str, log: Callable[[str], None]) -> bool:
        """尝试 Dispatch 一个 ProgID,成功即视为引擎可用。"""
        import gc
        import time

        import win32com.client

        try:
            app = win32com.client.Dispatch(prog_id)
            with contextlib.suppress(Exception):
                app.Quit()  # Quit 失败不影响"引擎可用"的判定
            return True
        except Exception as e:
            log(f"{e}")
            return False
        finally:
            gc.collect()
            time.sleep(0.1)

    @staticmethod
    def _probe_registry(prog_id: str) -> bool:
        """注册表探测:HKCR 下是否存在该 ProgID(毫秒级,不启动任何进程)。

        作为快速预筛——"注册了"基本等于"装了";更强证据由转换期真实 Dispatch
        成功后喂养(record_engine_evidence)。非 Windows 或 winreg 不可用时返回 False。
        """
        try:
            import winreg
        except ImportError:
            return False  # 非 Windows
        try:
            key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

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
        """
        launch_flight = False
        with EngineManager._flight_lock:
            if EngineManager._flight_subscribers is None:
                EngineManager._flight_subscribers = []
                launch_flight = True
            if callback is not None:
                EngineManager._flight_subscribers.append(callback)
        if launch_flight:
            # daemon=True: 进程退出时无需等待,避免测试/关闭时悬挂
            threading.Thread(target=self._run_async_detect, daemon=True).start()

    def _run_async_detect(self) -> None:
        """后台线程入口:CoInitialize 配对 + single-flight 投递。"""
        com_inited = False
        try:
            import pythoncom

            pythoncom.CoInitialize()
            com_inited = True
        except Exception:
            com_inited = False  # 非 Windows / 无 pywin32
        try:
            self._serve_flight()
        finally:
            if com_inited:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

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
        """通用初始化逻辑,由 init_word/excel/ppt 复用。"""
        if sys.platform != "win32":
            raise RuntimeError("此功能仅支持 Windows 系统")

        spec = _APP_CONFIG[kind]
        current_app = getattr(self, spec.app_attr)
        target_prog_id = self._get_prog_id(kind, engine)

        # 已有实例且引擎未变:直接复用
        if current_app is not None and getattr(self, spec.engine_attr) == target_prog_id:
            return current_app

        # 引擎切换:先释放旧实例
        if current_app is not None:
            with contextlib.suppress(Exception):
                current_app.Quit()
            setattr(self, spec.app_attr, None)
            setattr(self, spec.engine_attr, None)

        last_error = None
        for prog_id in self._prog_ids_to_try(kind, engine):
            try:
                # 最内层 Dispatch + Visible/DisplayAlerts 复用共享辅助(行为等价于原
                # app = win32com.client.Dispatch(prog_id); app.Visible=False;
                # app.DisplayAlerts=False)。缓存/fallback/属性 setattr 仍在此处。
                app = init_office_app(prog_id)
                setattr(self, spec.app_attr, app)
                setattr(self, spec.engine_attr, prog_id)
                # 真实 Dispatch 成功是最强证据:精确喂养该引擎键(record_engine_
                # evidence 保证不抛,不会把成功转换误入下方回退分支)。Dispatch
                # 失败的分支不记录 False——临时忙与装坏不可区分,由回退循环兜底。
                suite = _engine_suite_for_prog_id(prog_id)
                if suite is not None:
                    self.record_engine_evidence(suite, True)
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
        """关闭Office应用。

        _from_del:由 __del__ 调用时为 True,此时跳过末尾的 gc.collect()——在 GC 链中
        再触发 gc.collect() 会与 pywin32/Windows 堆交互导致 0xc0000374 堆损坏。
        """
        import gc
        import time

        errors: list[Exception] = []
        for spec in _APP_CONFIG.values():
            app = getattr(self, spec.app_attr, None)
            if app is not None:
                try:
                    app.Quit()
                except Exception as e:
                    self.logger.error(f"关闭{spec.label}应用失败: {e}")
                    errors.append(e)
                setattr(self, spec.app_attr, None)
                setattr(self, spec.engine_attr, None)

        # 强制垃圾回收,确保COM对象被释放。
        # 注意:不可在 __del__ 触发的 GC 链里调用——Windows + pywin32 下会堆损坏。
        if not _from_del:
            gc.collect()
            time.sleep(0.1)
        if strict and not _from_del and errors:
            raise ExceptionGroup("Office 释放失败: " + "; ".join(map(str, errors)), errors)

    def __del__(self) -> None:  # pragma: no cover
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close(_from_del=True)
