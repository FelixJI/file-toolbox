"""GUI 独立入口(供 Nuitka/Velopack 打包)。"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from file_toolbox.common.paths import GuiDataRootPolicy, use_data_root_policy
from file_toolbox.common.runtime import is_packaged_runtime

# 显式 --selftest 的合法模式(成品验证专用,正常用户启动不传这些参数)
_SELFTEST_MODES = ("pure", "full", "reopen")


def _parse_selftest_args(args: list[str]) -> tuple[str | None, Path | None]:
    """解析显式 --selftest/--selftest-report 参数;其余参数忽略(不影响正常启动)。

    argparse 的 fail-closed 语义:缺值/非法模式直接以退出码 2 终止并输出原因,
    绝不静默降级为正常 GUI 启动(正常启动可能触发真实更新检查);孤立的
    --selftest-report(无 --selftest)同样拒绝,避免自测报告参数误入普通启动。
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--selftest", choices=_SELFTEST_MODES)
    parser.add_argument("--selftest-report", type=Path)
    known, _unknown = parser.parse_known_args(args)
    if known.selftest is None and known.selftest_report is not None:
        parser.error("--selftest-report 必须与 --selftest 一起使用")
    return known.selftest, known.selftest_report


def _program_dir() -> Path:
    """程序所在目录,作为 GUI 持久数据根。

    打包形态取 exe 所在目录;Velopack 便携布局中 exe 位于 ``<root>/current/``,
    数据须落在 ``current/`` 之外以免被更新替换。源码运行取仓库根
    (``file_toolbox`` 包的上级)。Nuitka 下 ``sys.executable`` 是合成的
    ``<dist>/python.exe`` 路径,取其目录仍能得到正确的 dist 布局。
    """
    if not is_packaged_runtime():
        return Path(__file__).resolve().parent.parent
    exe_dir = Path(sys.executable).parent
    if exe_dir.name == "current":
        exe_dir = exe_dir.parent
    return exe_dir


@contextmanager
def prepare_gui_runtime(
    *, packaged: bool | None = None, program_dir: Path | None = None, home: Path | None = None
) -> Iterator[None]:
    """数据根固定为程序目录;打包入口同时把 cwd 固定到用户 home。"""

    is_packaged = is_packaged_runtime() if packaged is None else packaged
    gui_home = Path.home() if home is None else home
    base_dir = _program_dir() if program_dir is None else program_dir
    original_cwd = Path.cwd()
    gui_home.mkdir(parents=True, exist_ok=True)
    if is_packaged:
        os.chdir(gui_home)
    try:
        with use_data_root_policy(GuiDataRootPolicy(base_dir)):
            yield
    finally:
        if is_packaged:
            os.chdir(original_cwd)


def _source_selftest_root() -> Path:
    """源码形态 selftest 的新虚构数据根(不写现用配置/历史)。

    优先取 ``FILE_TOOLBOX_SELFTEST_DATA_ROOT`` 环境变量(需要跨两次启动共享
    同一根时由调用方显式指定);否则在仓库声明的构建输出目录下新建本进程专属
    子目录,不删除任何既有内容。打包形态不经过本函数——便携目录本身就是
    成品自测要验证的真实数据根。
    """
    override = os.environ.get("FILE_TOOLBOX_SELFTEST_DATA_ROOT")
    if override:
        return Path(override)
    from datetime import UTC, datetime

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path(__file__).resolve().parent.parent / "build" / "selftest-runtime"
    return root / f"run-{stamp}-{os.getpid()}"


def _run_velopack_hooks() -> bool:
    """打包形态下执行 Velopack hook(--veloapp-install/obsolete/updated 等)。

    hook 进程只处理参数后即退出,不创建任何窗口;漏跑的后果是更新器只能
    15s 超时强杀一个被完整拉起的 GUI(0.2.9-0.2.11 的实际故障:Nuitka 不设
    ``sys.frozen``,旧 gate 把便携包当成源码运行而跳过本调用)。返回是否执行。
    """
    if not is_packaged_runtime():
        return False
    import velopack

    velopack.App().run()
    return True


def _run_gui_entry(selftest_mode: str | None, selftest_report: Path | None) -> None:
    """真实启动体:数据根门禁 → 日志 → Velopack hook → GUI/selftest。"""
    import logging
    import time

    if selftest_mode is not None:
        # 显式自测门禁(F2):在任何 GUI/日志写入之前拒绝已存在的真实数据根,
        # 且不改动该目录;源码隔离根/新解包便携根则写入最小自测范围标记。
        from file_toolbox.gui.selftest_driver import ensure_selftest_data_root

        allowed, reason = ensure_selftest_data_root()
        if not allowed:
            print(f"::error::{reason}", file=sys.stderr)
            raise SystemExit(1)

    # 日志必须最先就绪:偶发启动卡死时,最后一个完成的阶段日志即卡死位置。
    from file_toolbox.common.logging_config import configure_logging

    # 不能用 __name__:作为入口执行(python -m file_toolbox.gui_entry 或
    # PyInstaller 入口脚本)时 __name__ 是 "__main__",对应的 logger 不在配置了
    # 文件 handler 的 file_toolbox 树下,启动各阶段留痕会静默丢失。
    logger = logging.getLogger("file_toolbox.gui_entry")
    log_file = configure_logging(mode="gui")
    logger.info(
        "GUI 入口 packaged=%s pid=%s exe=%s log=%s",
        is_packaged_runtime(),
        os.getpid(),
        sys.executable,
        log_file,
    )
    # 必须早于 Qt、settings 等应用初始化(logging 只写文件,不属于应用状态)。
    t0 = time.perf_counter()
    if _run_velopack_hooks():
        logger.info("Velopack hook 完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter()
    from file_toolbox.gui.main_window import run_gui

    logger.info("GUI 模块导入完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    if selftest_mode is None:
        run_gui()
        return
    # 成品自测分支:真实启动链(数据根/日志/Velopack hook/单实例/watchdog)全部
    # 保留,仅由 driver 注入 fake 更新协调器;selftest 模块只在此分支 lazy
    # import,正常启动不加载。
    from file_toolbox.gui.selftest_driver import make_selftest_driver

    run_gui(selftest_driver=make_selftest_driver(selftest_mode, selftest_report))


def main() -> None:
    """运行 GUI;日志先于 Velopack hook 与 GUI 导入配置,启动各阶段留痕。"""

    # 显式参数分支:缺值/非法模式由 argparse 以退出码 2 fail closed。
    selftest_mode, selftest_report = _parse_selftest_args(sys.argv[1:])
    if selftest_mode is not None and not is_packaged_runtime():
        # 源码形态 selftest:数据根隔离到新虚构目录,绝不写仓库/现用配置与历史;
        # 打包形态走下方默认 prepare_gui_runtime(便携目录即被验证的真实数据根)。
        with prepare_gui_runtime(program_dir=_source_selftest_root()):
            _run_gui_entry(selftest_mode, selftest_report)
        return
    with prepare_gui_runtime():
        _run_gui_entry(selftest_mode, selftest_report)


if __name__ == "__main__":  # pragma: no cover
    main()
