"""GUI 独立入口（供 PyInstaller/Velopack 打包）。"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from file_toolbox.common.paths import GuiDataRootPolicy, use_data_root_policy


@contextmanager
def prepare_gui_runtime(*, frozen: bool | None = None, home: Path | None = None) -> Iterator[None]:
    """稳定 GUI 数据根；frozen 入口同时把 cwd 固定到用户 home。"""

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    gui_home = Path.home() if home is None else home
    original_cwd = Path.cwd()
    gui_home.mkdir(parents=True, exist_ok=True)
    if is_frozen:
        os.chdir(gui_home)
    try:
        with use_data_root_policy(GuiDataRootPolicy(gui_home)):
            yield
    finally:
        if is_frozen:
            os.chdir(original_cwd)


def main() -> None:
    """运行 GUI；frozen 时先执行 Velopack hook，所有 GUI 形态使用 home data root。"""

    if getattr(sys, "frozen", False):
        # 必须早于 Qt、logging、settings 等应用初始化。
        import velopack

        velopack.App().run()
    with prepare_gui_runtime():
        from file_toolbox.gui.main_window import run_gui

        run_gui()


if __name__ == "__main__":  # pragma: no cover
    main()
