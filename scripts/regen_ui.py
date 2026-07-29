"""UI 再生链路 + 漂移检测:用 pyside6-uic 从 .ui 正向再生成 ui_*.py。

本脚本解决「生成式 UI 无源可编译」的单向棘轮债务:把 .ui → ui_*.py 的再生成
变成可重复、可检测漂移的过程。

运行方式(须带 --extra dev,因为 pyside6-uic 在 dev 依赖的 venv 里):
  uv run --extra dev python scripts/regen_ui.py            # 正向再生成所有 .ui
  uv run --extra dev python scripts/regen_ui.py --check    # CI 漂移检测,不写盘

两类 ui_*.py:
  - **有 .ui 源**:pyside6-uic 可正向再生成。--check 比对 AST 规范化后的结果
    与已提交文件,不一致则 exit 1。
  - **手维护源(HANDMADE)**:无 .ui(如发票 tab 是手写布局)。--check 跳过它们,
    不要求 uic 再生。这种文件应在头部注释里诚实标注「手维护、无 .ui」。

关键设计:在没有 .ui 时 --check 也安全通过(不报错),这样能先建立检测链路、
后续逐步补 .ui。漂移检测用 AST 规范化(见 _normalize_ast),对 uic 的若干纯
表面差异(单/多行 import、`u""` 前缀、uic 的 unicode 转义 vs 原字面、`(object)` 基类、
编译器版本号、`# -*- coding -*-` 行)归一,避免误报。
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FORMS_DIR = _ROOT / "file_toolbox" / "gui" / "forms"
_GENERATED_DIR = _ROOT / "file_toolbox" / "gui" / "generated"


@dataclass(frozen=True)
class UiMapping:
    """一个 .ui 源 → 一个生成的 ui_*.py 的映射。

    ui_module: 生成的 ui_*.py 文件名(相对 _GENERATED_DIR),如 "ui_mkdir_dialog.py"。
    ui_file:   源 .ui 文件名(相对 _FORMS_DIR),如 "batch_folder_creator_dialog.ui"。
    """

    ui_module: str
    ui_file: str


# .ui 源 → 生成模块的映射表(声明式)。
# 仓库里历史上 ui_*.py 头部声称的 .ui 文件名记录于此;当为对应模块补齐 .ui 后,
# 该映射即生效(否则 _FORMS_DIR 下找不到该 .ui,该模块按手维护处理)。
UI_SOURCES: list[UiMapping] = [
    UiMapping(
        ui_module="ui_mkdir_dialog.py",
        ui_file="batch_folder_creator_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_pdf_dialog.py",
        ui_file="ui_pdf_generator_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_rename_dialog.py",
        ui_file="file_renamer_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_replace_dialog.py",
        ui_file="content_replace_dialog.ui",
    ),
]

# 手维护源清单:无 .ui、由人工维护布局代码的 ui_*.py。--check 跳过这些文件。
# 把某模块列入此处等价于声明「该模块不走 uic 再生」;补齐 .ui 后应将其移出。
# 已接入 .ui 再生的模块(如 ui_mkdir_dialog.py)不在此清单中。
# 其余 dialog(pdf/rename/replace)历史文件含手写惯用法(setHorizontalHeaderLabels 等),
# pyside6-uic 无法精确复现,在补齐 .ui 前暂归手维护。详见 task-6-report.md。
HANDMADE: set[str] = {
    "ui_invoice_dialog.py",
    "ui_pdf_dialog.py",
    "ui_rename_dialog.py",
    "ui_replace_dialog.py",
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _normalize_ast(source: str) -> str:
    """把 Python 源码解析为 AST 再 unparse,得到与表面格式无关的规范表示。

    pyside6-uic 的输出与人工/旧版本生成的 ui_*.py 之间,存在若干不影响语义的
    表面差异。直接文本比对会产生大量误报,故这里做 AST 级归一:
      - `class Ui_X(object)` 与 `class Ui_X` → 去掉显式 object 基类;
      - `u"字面"` 与 `"字面"` → ast 不区分前缀,值相同;
      - uic 的 unicode 转义(如 uXXXX 形式)与原字面汉字 → 二者解析为同一字符串;
      - 单/多行 import、空行、`# -*- coding -*-` 注释 → ast.unparse 统一格式化。

    用 AST 比较(而非 exec/导入)可避免实际创建 QWidget 时的副作用与 Qt 环境依赖,
    也无需导入业务包。若 source 非法 Python 抛 SyntaxError(让调用方处理)。
    """
    tree = ast.parse(source)
    # 去掉显式 `(object)` 基类,使 `class X(object)` 与 `class X` 等价。
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            node.bases = [
                base
                for base in node.bases
                if not (isinstance(base, ast.Name) and base.id == "object")
            ]
        # 抹掉字符串字面的前缀(u/b/f 等):ast.Constant.kind 记录前缀种类,
        # uic 输出带 u 前缀,人工文件通常没有。置 None 让 unparse 统一为无前缀。
        if isinstance(node, ast.Constant) and getattr(node, "kind", None) is not None:
            node.kind = None
    return ast.unparse(tree)


def _run_uic(ui_path: Path, output_path: Path) -> None:
    """调用 pyside6-uic 把 ui_path 编译为 output_path。失败抛 RuntimeError。"""
    if shutil.which("pyside6-uic") is None:
        # CI/本地:dev venv 里 pyside6-uic 已随 PySide6 安装;给清晰报错。
        raise RuntimeError(
            "未找到 pyside6-uic 可执行文件。请在 dev 环境运行:"
            " uv run --extra dev python scripts/regen_ui.py"
        )
    proc = subprocess.run(
        ["pyside6-uic", str(ui_path), "-o", str(output_path)],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pyside6-uic 失败({proc.returncode})处理 {ui_path}:\n{proc.stdout}\n{proc.stderr}"
        )


def _active_mappings() -> list[tuple[UiMapping, Path]]:
    """返回 [(mapping, ui_path)] 列表,仅含 .ui 文件实际存在的映射。

    无 .ui 的映射被忽略(对应模块按手维护处理)。无任何 .ui 时返回空列表。
    """
    active: list[tuple[UiMapping, Path]] = []
    for m in UI_SOURCES:
        ui_path = _FORMS_DIR / m.ui_file
        if ui_path.is_file():
            active.append((m, ui_path))
    return active


def _ui_in_handmade(module: str) -> bool:
    """模块是否在 HANDMADE 手维护清单里。"""
    return module in HANDMADE


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------


def cmd_regen() -> int:
    """正向再生成:对每个 .ui 跑 pyside6-uic 写出对应 ui_*.py。

    手维护源(在 HANDMADE 里)不参与;无 .ui 时打印提示并正常返回。
    """
    active = _active_mappings()
    if not active:
        print("无 .ui 源文件,跳过再生成(所有 ui_*.py 当前为手维护)。")
        return 0

    written: list[str] = []
    skipped_handmade: list[str] = []
    for m, ui_path in active:
        out = _GENERATED_DIR / m.ui_module
        if _ui_in_handmade(m.ui_module):
            # 有 .ui 但仍标记手维护 → 视为「已补 .ui 但尚未移出 HANDMADE」,
            # 仍然再生成(补 .ui 即表示接管该文件)。这是促使移出 HANDMADE 的路径。
            print(f"注意: {m.ui_module} 在 HANDMADE 清单中,但已发现 .ui 源 → 再生成并接管。")
        _run_uic(ui_path, out)
        written.append(f"  {m.ui_file} → generated/{m.ui_module}")

    # 其余在 HANDMADE 里的模块(无 .ui):提示手维护
    for m in UI_SOURCES:
        if _ui_in_handmade(m.ui_module) and not (_FORMS_DIR / m.ui_file).is_file():
            skipped_handmade.append(f"  generated/{m.ui_module}(手维护,无 .ui)")

    if written:
        print("已再生成:")
        print("\n".join(written))
    if skipped_handmade:
        print("以下为手维护源(无 .ui,未参与再生成):")
        print("\n".join(skipped_handmade))
    return 0


def cmd_check() -> int:
    """漂移检测:对每个 .ui 用 pyside6-uic 生成到临时内存,比对 AST 规范化结果。

    不写盘。与已提交 ui_*.py 不一致 → 打印差异并 exit 1(CI 用)。
    手维护源(HANDMADE)跳过。无 .ui 时直接通过(建立链路、待后续补 .ui)。
    """
    active = _active_mappings()
    if not active:
        print("无 .ui 源文件,跳过漂移检测(全部为手维护)。check 通过。")
        return 0

    drift_count = 0
    checked: list[str] = []
    for m, ui_path in active:
        out_path = _GENERATED_DIR / m.ui_module
        if not out_path.is_file():
            print(f"错误: 生成的目标不存在 generated/{m.ui_module}", file=sys.stderr)
            drift_count += 1
            continue
        # uic 生成到临时文件,读文本后即删
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_uic(ui_path, tmp_path)
            generated_text = tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)

        committed_text = out_path.read_text(encoding="utf-8")
        try:
            gen_norm = _normalize_ast(generated_text)
            committed_norm = _normalize_ast(committed_text)
        except SyntaxError as e:
            print(
                f"错误: 解析 generated/{m.ui_module} 失败(SyntaxError): {e}",
                file=sys.stderr,
            )
            drift_count += 1
            continue

        if gen_norm != committed_norm:
            drift_count += 1
            print(f"漂移: generated/{m.ui_module} 与 .ui 源的 uic 输出不一致。", file=sys.stderr)
            print(
                "  运行 `uv run --extra dev python scripts/regen_ui.py` 再生成,"
                "或确认改动为有意为之后更新 .ui。",
                file=sys.stderr,
            )
        else:
            checked.append(f"  generated/{m.ui_module} ✓")

    handmade_no_ui = [
        f"  generated/{m.ui_module}"
        for m in UI_SOURCES
        if _ui_in_handmade(m.ui_module) and not (_FORMS_DIR / m.ui_file).is_file()
    ]

    if checked:
        print("漂移检测通过(有 .ui 源的模块):")
        print("\n".join(checked))
    if handmade_no_ui:
        print("手维护源(无 .ui,已跳过):")
        print("\n".join(handmade_no_ui))

    if drift_count > 0:
        print(f"\n失败: {drift_count} 个模块存在 UI 漂移。", file=sys.stderr)
        return 1
    print("\n全部通过: 无 UI 漂移。")
    return 0


def cmd_list() -> int:
    """列出已知的 ui_*.py、其 .ui 源状态、是否手维护(便于人工核对)。"""
    print("UI 源清单:")
    print(f"  forms 目录: {_FORMS_DIR}")
    print(f"  生成目录:   {_GENERATED_DIR}")
    print()
    print(f"{'ui_*.py':<28} {'状态':<14} .ui 源")
    print("-" * 72)
    # 先列有映射的,再列 invoice(无映射、纯手维护)
    seen: set[str] = set()
    for m in UI_SOURCES:
        seen.add(m.ui_module)
        ui_path = _FORMS_DIR / m.ui_file
        exists = ui_path.is_file()
        handmade = _ui_in_handmade(m.ui_module)
        if exists and not handmade:
            status = "uic 再生"
        elif exists and handmade:
            status = "uic(待移出)"
        else:
            status = "手维护"
        ui_display = m.ui_file + (" (已补)" if exists else " (缺失)")
        print(f"  {m.ui_module:<26} {status:<14} {ui_display}")
    # generated 下存在但未登记的 ui_*.py
    for p in sorted(_GENERATED_DIR.glob("ui_*.py")):
        if p.name in seen:
            continue
        print(f"  {p.name:<26} {'手维护':<14} (未登记 .ui)")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="regen_ui.py",
        description="UI 再生链路 + 漂移检测(.ui → ui_*.py via pyside6-uic)。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="漂移检测模式:不写盘,比对 uic 输出与已提交 ui_*.py,不一致则 exit 1(CI 用)。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出已知 ui_*.py、其 .ui 源状态与是否手维护。",
    )
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()
    if args.list:
        return cmd_list()
    return cmd_regen()


if __name__ == "__main__":
    raise SystemExit(main())
