"""GUI 独立入口（供 PyInstaller/Velopack 打包）。"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from file_toolbox.common.paths import GuiDataRootPolicy, use_data_root_policy


def _program_dir() -> Path:
    """程序所在目录，作为 GUI 持久数据根。

    frozen 取 exe 所在目录；Velopack 便携布局中 exe 位于 ``<root>/current/``，
    数据须落在 ``current/`` 之外以免被更新替换。源码运行取仓库根
    (``file_toolbox`` 包的上级)。
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    exe_dir = Path(sys.executable).parent
    if exe_dir.name == "current":
        exe_dir = exe_dir.parent
    return exe_dir


@contextmanager
def prepare_gui_runtime(
    *, frozen: bool | None = None, program_dir: Path | None = None, home: Path | None = None
) -> Iterator[None]:
    """数据根固定为程序目录；frozen 入口同时把 cwd 固定到用户 home。"""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    gui_home = Path.home() if home is None else home
    base_dir = _program_dir() if program_dir is None else program_dir
    original_cwd = Path.cwd()
    gui_home.mkdir(parents=True, exist_ok=True)
    if is_frozen:
        os.chdir(gui_home)
    try:
        with use_data_root_policy(GuiDataRootPolicy(base_dir)):
            yield
    finally:
        if is_frozen:
            os.chdir(original_cwd)


def main() -> None:
    """运行 GUI;日志先于 Velopack hook 与 GUI 导入配置,启动各阶段留痕。"""

    import logging
    import time

    with prepare_gui_runtime():
        # 日志必须最先就绪:偶发启动卡死时,最后一个完成的阶段日志即卡死位置。
        from file_toolbox.common.logging_config import configure_logging

        # 不能用 __name__:作为入口执行(python -m file_toolbox.gui_entry 或
        # PyInstaller 入口脚本)时 __name__ 是 "__main__",对应的 logger 不在配置了
        # 文件 handler 的 file_toolbox 树下,启动各阶段留痕会静默丢失。
        logger = logging.getLogger("file_toolbox.gui_entry")
        log_file = configure_logging(mode="gui")
        logger.info(
            "GUI 入口 frozen=%s pid=%s exe=%s log=%s",
            bool(getattr(sys, "frozen", False)),
            os.getpid(),
            sys.executable,
            log_file,
        )
        if getattr(sys, "frozen", False):
            # 必须早于 Qt、settings 等应用初始化(logging 只写文件,不属于应用状态)。
            import velopack

            t0 = time.perf_counter()
            velopack.App().run()
            logger.info("Velopack hook 完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        from file_toolbox.gui.main_window import run_gui

        logger.info("GUI 模块导入完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
        run_gui()


if __name__ == "__main__":  # pragma: no cover
    main()
