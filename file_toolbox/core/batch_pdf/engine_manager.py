"""
Office引擎管理器

负责检测和初始化 Microsoft Office / WPS Office 应用
"""

import contextlib
import sys

from file_toolbox.common.loggable import LoggableMixin

from .constants import ENGINE_AUTO, ENGINE_WPS


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

    def _detect_available_engines(self, force_refresh: bool = False) -> dict[str, bool]:
        """检测可用的Office引擎（带缓存）"""
        if EngineManager._cached_engines is not None and not force_refresh:
            return EngineManager._cached_engines

        import win32com.client

        engines = {"office": False, "wps": False}

        # 检测Microsoft Office Word
        # 只要Dispatch成功就说明引擎可用，Quit()失败不应影响检测结果
        try:
            word = win32com.client.Dispatch("Word.Application")
            engines["office"] = True
            try:
                word.Quit()
            except Exception:
                pass  # 忽略退出时的错误
            finally:
                word = None
        except Exception as e:
            self.logger.warning(f"检测Microsoft Office Word失败: {e}")
        finally:
            # 强制垃圾回收,确保COM对象被释放
            import gc
            import time

            gc.collect()
            time.sleep(0.1)

        # 检测WPS Office (使用KWPS.Application)
        # 只要Dispatch成功就说明引擎可用，Quit()失败不应影响检测结果
        try:
            wps = win32com.client.Dispatch("KWPS.Application")
            engines["wps"] = True
            try:
                wps.Quit()
            except Exception:
                pass  # 忽略退出时的错误
            finally:
                wps = None
        except Exception as e:
            self.logger.warning(f"检测WPS Office失败: {e}")
        finally:
            # 强制垃圾回收,确保COM对象被释放
            import gc
            import time

            gc.collect()
            time.sleep(0.1)

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
        """异步检测引擎（在后台线程调用）"""
        self._detect_available_engines(force_refresh=True)
        if callback:
            callback(self.get_engine_info(use_cache=True))

    def _get_word_prog_id(self, engine: str = "auto") -> str:
        """获取Word的ProgID"""
        if engine == ENGINE_AUTO:
            engines = self._detect_available_engines()
            if engines["office"]:
                return "Word.Application"
            elif engines["wps"]:
                return "KWPS.Application"
            else:
                return "Word.Application"
        elif engine == ENGINE_WPS:
            return "KWPS.Application"
        else:  # ENGINE_MS_OFFICE
            return "Word.Application"

    def _get_excel_prog_id(self, engine: str = "auto") -> str:
        """获取Excel的ProgID"""
        if engine == ENGINE_AUTO:
            engines = self._detect_available_engines()
            if engines["office"]:
                return "Excel.Application"
            elif engines["wps"]:
                return "Ket.Application"
            else:
                return "Excel.Application"
        elif engine == ENGINE_WPS:
            return "Ket.Application"
        else:  # ENGINE_MS_OFFICE
            return "Excel.Application"

    def _get_ppt_prog_id(self, engine: str = "auto") -> str:
        """获取PowerPoint的ProgID"""
        if engine == ENGINE_AUTO:
            engines = self._detect_available_engines()
            if engines["office"]:
                return "PowerPoint.Application"
            elif engines["wps"]:
                return "KWPP.Application"
            else:
                return "PowerPoint.Application"
        elif engine == ENGINE_WPS:
            return "KWPP.Application"
        else:  # ENGINE_MS_OFFICE
            return "PowerPoint.Application"

    def init_word(self, engine: str = "auto"):
        """初始化Word应用，支持引擎切换"""
        if sys.platform != "win32":
            raise RuntimeError("此功能仅支持 Windows 系统")

        target_prog_id = self._get_word_prog_id(engine)

        if self._word_app is not None and self._current_word_engine == target_prog_id:
            return self._word_app

        if self._word_app is not None:
            with contextlib.suppress(Exception):
                self._word_app.Quit()
            self._word_app = None
            self._current_word_engine = None

        import win32com.client

        prog_ids_to_try = []
        if engine == ENGINE_AUTO:
            prog_ids_to_try = ["Word.Application", "KWPS.Application"]
        elif engine == ENGINE_WPS:
            prog_ids_to_try = ["KWPS.Application", "Word.Application"]
        else:  # ENGINE_MS_OFFICE
            prog_ids_to_try = ["Word.Application", "KWPS.Application"]

        last_error = None
        for prog_id in prog_ids_to_try:
            try:
                self._word_app = win32com.client.Dispatch(prog_id)
                self._word_app.Visible = False
                self._word_app.DisplayAlerts = False
                self._current_word_engine = prog_id
                return self._word_app
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"无法启动 Word 应用程序。请确保已安装 Microsoft Office 或 WPS Office。\n"
            f"详细错误: {last_error}"
        )

    def init_excel(self, engine: str = "auto"):
        """初始化Excel应用，支持引擎切换"""
        if sys.platform != "win32":
            raise RuntimeError("此功能仅支持 Windows 系统")

        target_prog_id = self._get_excel_prog_id(engine)

        if self._excel_app is not None and self._current_excel_engine == target_prog_id:
            return self._excel_app

        if self._excel_app is not None:
            with contextlib.suppress(Exception):
                self._excel_app.Quit()
            self._excel_app = None
            self._current_excel_engine = None

        import win32com.client

        prog_ids_to_try = []
        if engine == ENGINE_AUTO:
            prog_ids_to_try = ["Excel.Application", "Ket.Application"]
        elif engine == ENGINE_WPS:
            prog_ids_to_try = ["Ket.Application", "Excel.Application"]
        else:  # ENGINE_MS_OFFICE
            prog_ids_to_try = ["Excel.Application", "Ket.Application"]

        last_error = None
        for prog_id in prog_ids_to_try:
            try:
                self._excel_app = win32com.client.Dispatch(prog_id)
                self._excel_app.Visible = False
                self._excel_app.DisplayAlerts = False
                self._current_excel_engine = prog_id
                return self._excel_app
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"无法启动 Excel 应用程序。请确保已安装 Microsoft Office 或 WPS Office。\n"
            f"详细错误: {last_error}"
        )

    def init_ppt(self, engine: str = "auto"):
        """初始化PowerPoint应用，支持引擎切换"""
        if sys.platform != "win32":
            raise RuntimeError("此功能仅支持 Windows 系统")

        target_prog_id = self._get_ppt_prog_id(engine)

        if self._ppt_app is not None and self._current_ppt_engine == target_prog_id:
            return self._ppt_app

        if self._ppt_app is not None:
            with contextlib.suppress(Exception):
                self._ppt_app.Quit()
            self._ppt_app = None
            self._current_ppt_engine = None

        import win32com.client

        prog_ids_to_try = []
        if engine == ENGINE_AUTO:
            prog_ids_to_try = ["PowerPoint.Application", "KWPP.Application"]
        elif engine == ENGINE_WPS:
            prog_ids_to_try = ["KWPP.Application", "PowerPoint.Application"]
        else:  # ENGINE_MS_OFFICE
            prog_ids_to_try = ["PowerPoint.Application", "KWPP.Application"]

        last_error = None
        for prog_id in prog_ids_to_try:
            try:
                self._ppt_app = win32com.client.Dispatch(prog_id)
                self._current_ppt_engine = prog_id
                return self._ppt_app
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"无法启动 PowerPoint 应用程序。请确保已安装 Microsoft Office 或 WPS Office。\n"
            f"详细错误: {last_error}"
        )

    def close(self):
        """关闭Office应用"""
        import gc
        import time

        try:
            if self._word_app is not None:
                self._word_app.Quit()
                self._word_app = None
        except Exception as e:
            self.logger.error(f"关闭Word应用失败: {e}")

        try:
            if self._excel_app is not None:
                self._excel_app.Quit()
                self._excel_app = None
        except Exception as e:
            self.logger.error(f"关闭Excel应用失败: {e}")

        try:
            if self._ppt_app is not None:
                self._ppt_app.Quit()
                self._ppt_app = None
        except Exception as e:
            self.logger.error(f"关闭PowerPoint应用失败: {e}")

        # 强制垃圾回收,确保COM对象被释放
        gc.collect()
        time.sleep(0.1)

    def __del__(self):
        """析构函数"""
        with contextlib.suppress(Exception):
            self.close()
