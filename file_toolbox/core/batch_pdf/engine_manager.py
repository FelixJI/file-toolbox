"""
Office引擎管理器

负责检测和初始化 Microsoft Office / WPS Office 应用
"""

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass

from file_toolbox.common.loggable import LoggableMixin

from .constants import ENGINE_AUTO, ENGINE_WPS


@dataclass(frozen=True)
class _AppSpec:
    """单个 Office 应用的配置(app 实例属性、引擎属性、各引擎 ProgID、检测用 ProgID)。"""

    kind: str               # word | excel | ppt
    app_attr: str           # self._word_app 等
    engine_attr: str        # self._current_word_engine 等
    ms_prog_id: str         # Microsoft Office ProgID
    wps_prog_id: str        # WPS Office ProgID
    label: str              # 错误提示用名


# 三种应用的配置表 —— 新增应用只需在此添加一行。
_APP_CONFIG: dict[str, _AppSpec] = {
    "word": _AppSpec("word", "_word_app", "_current_word_engine",
                     "Word.Application", "KWPS.Application", "Word"),
    "excel": _AppSpec("excel", "_excel_app", "_current_excel_engine",
                      "Excel.Application", "Ket.Application", "Excel"),
    "ppt": _AppSpec("ppt", "_ppt_app", "_current_ppt_engine",
                    "PowerPoint.Application", "KWPP.Application", "PowerPoint"),
}


class EngineManager(LoggableMixin):
    """Office引擎管理器"""

    # 缓存检测结果（类变量，所有实例共享）
    _cached_engines: dict[str, bool] | None = None

    def __init__(self):
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
            try:
                app.Quit()
            except Exception:
                pass  # Quit 失败不影响"引擎可用"的判定
            return True
        except Exception as e:
            log(f"{e}")
            return False
        finally:
            gc.collect()
            time.sleep(0.1)

    def _detect_available_engines(self, force_refresh: bool = False) -> dict[str, bool]:
        """检测可用的Office引擎（带缓存）"""
        if EngineManager._cached_engines is not None and not force_refresh:
            return EngineManager._cached_engines

        engines = {
            "office": self._try_detect(
                "Word.Application", lambda m: self.logger.warning(f"检测Microsoft Office Word失败: {m}")
            ),
            "wps": self._try_detect(
                "KWPS.Application", lambda m: self.logger.warning(f"检测WPS Office失败: {m}")
            ),
        }

        # 缓存结果
        EngineManager._cached_engines = engines
        return engines

    def get_engine_info(self, use_cache: bool = True) -> str:
        """获取当前引擎信息"""
        if use_cache and EngineManager._cached_engines is None:
            return "正在检测可用引擎..."

        engines = self._detect_available_engines(force_refresh=not use_cache)
        info_parts = []

        if engines["office"]:
            info_parts.append("MS Office (Microsoft Print To PDF)")
        if engines["wps"]:
            info_parts.append("WPS (Kingsoft Virtual Printer)")

        if not info_parts:
            return "未检测到Office软件"

        return "可用引擎: " + "、".join(info_parts)

    def detect_engines_async(self, callback=None):
        """异步检测引擎(在后台守护线程执行,不阻塞调用线程)。

        检测需 Dispatch COM 进程外服务器(Word/WPS),既慢又可能在没有桌面/Office
        的环境(CI、无头会话)中失败,故必须在后台线程运行:既避免冻结 GUI 主线程,
        也让调用方(含测试)不必在调用线程触发实时 COM。回调在该后台线程触发,调用方
        应自行切回主线程更新 UI(pdf_tab 已用 QTimer.singleShot(0,...) 处理)。

        COM 注意:win32com 要求使用它的每个线程先 CoInitialize,否则进程退出时
        抛 CO_E_NOTINITIALIZED(0x800401f0)致命异常。故 worker 入口/出口配对调用。
        """
        import threading

        def _worker():
            import pythoncom

            pythoncom.CoInitialize()
            try:
                self._detect_available_engines(force_refresh=True)
                if callback:
                    callback(self.get_engine_info(use_cache=True))
            except Exception as e:  # COM/线程异常不应波及调用线程
                self.logger.warning(f"异步引擎检测失败: {e}")
            finally:
                pythoncom.CoUninitialize()

        # daemon=True: 进程退出时无需等待,避免测试/关闭时悬挂
        threading.Thread(target=_worker, daemon=True).start()

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

    def _init_office_app(self, kind: str, engine: str = ENGINE_AUTO):
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

        import win32com.client

        last_error = None
        for prog_id in self._prog_ids_to_try(kind, engine):
            try:
                app = win32com.client.Dispatch(prog_id)
                app.Visible = False
                app.DisplayAlerts = False
                setattr(self, spec.app_attr, app)
                setattr(self, spec.engine_attr, prog_id)
                return app
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"无法启动 {spec.label} 应用程序。请确保已安装 Microsoft Office 或 WPS Office。\n"
            f"详细错误: {last_error}"
        )

    def init_word(self, engine: str = ENGINE_AUTO):
        """初始化Word应用，支持引擎切换"""
        return self._init_office_app("word", engine)

    def init_excel(self, engine: str = ENGINE_AUTO):
        """初始化Excel应用，支持引擎切换"""
        return self._init_office_app("excel", engine)

    def init_ppt(self, engine: str = ENGINE_AUTO):
        """初始化PowerPoint应用，支持引擎切换"""
        return self._init_office_app("ppt", engine)

    def close(self):
        """关闭Office应用"""
        import gc
        import time

        for spec in _APP_CONFIG.values():
            app = getattr(self, spec.app_attr, None)
            if app is not None:
                try:
                    app.Quit()
                except Exception as e:
                    self.logger.error(f"关闭{spec.label}应用失败: {e}")
                setattr(self, spec.app_attr, None)
                setattr(self, spec.engine_attr, None)

        # 强制垃圾回收,确保COM对象被释放
        gc.collect()
        time.sleep(0.1)

    def __del__(self):
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close()
