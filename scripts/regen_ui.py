"""UI 来源登记 + 再生成 + 漂移检测:用 pyside6-uic 从 .ui 正向再生成 ui_*.py。

generated/ 下全部 ui_*.py 的来源唯一,并在本脚本中显式登记:
  - **UI_SOURCES(真生成物)**:attendance/markdown/mkdir/plan_schedule。
    forms/ 下有对应 .ui,由 pyside6-uic 再生成;这些文件禁止手改。
    --check 用 AST 规范化(见 _normalize_ast)比对 uic 输出与已提交文件,
    不一致则 exit 1。
  - **HANDMADE(手写布局)**:excel_merge/invoice/pdf/pdf_sort/rename/replace。
    无 .ui、由人工维护,遵守仓库常规 Ruff/mypy 规则;本脚本不生成、不覆盖、
    不比对它们。要改走 .ui 生成链路,须先更新登记(移出 HANDMADE 并在
    UI_SOURCES 添加映射),不会出现「放入 .ui 即自动接管」。

fail closed 约定(两命令都先做分类完整性校验,见 _classification_errors):
  - 分类错误(已登记源丢失、未登记 ui_*.py、孤儿 .ui、重复/交叉登记、
    手写源缺失)→ --check 与 regen 都直接失败,不写盘、不覆盖任何文件;
    新增 .ui 也不会自动接管任何手写文件。
  - 生成物缺失或漂移 → 只由 --check 报告失败;这正是正常 regen 要修复的
    内容:重建缺失的生成目标、把漂移文件刷新回 .ui 派生状态。

运行方式(pyside6-uic 随 gui extra 的 PySide6 提供):
  uv run --all-extras python scripts/regen_ui.py            # 正向再生成真生成物
  uv run --all-extras python scripts/regen_ui.py --check    # 漂移 + 登记检测(CI 用)
  uv run --all-extras python scripts/regen_ui.py --list     # 列出全部登记清单
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# CI(如 GitHub Actions windows-latest,英文区域)控制台默认 cp1252,
# 无法编码脚本里的中文/✓/✗ 字符 → print 抛 UnicodeEncodeError。
# 把标准流重配为 UTF-8,使脚本不依赖控制台代码页(reconfigure 原地生效)。
# Python 3.7+。与 build_exe.py 同模式。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

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


# .ui 源 → 生成模块的映射表(声明式)。这是 generated/ 下全部「真生成物」的唯一
# 来源登记:每项的 .ui 必须存在于 forms/,目标必须只由 pyside6-uic 产出。
UI_SOURCES: list[UiMapping] = [
    UiMapping(
        ui_module="ui_attendance_dialog.py",
        ui_file="attendance_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_markdown_dialog.py",
        ui_file="markdown_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_mkdir_dialog.py",
        ui_file="batch_folder_creator_dialog.ui",
    ),
    UiMapping(
        ui_module="ui_plan_schedule_dialog.py",
        ui_file="plan_schedule_dialog.ui",
    ),
]

# 手写布局白名单:无 .ui、由人工维护的 ui_*.py,与仓库其余代码一样遵守
# Ruff/mypy 规则。本脚本对它们只做「存在性」校验,不生成、不覆盖、不比对;
# 新增 .ui 也不会自动接管这里的任何文件(孤儿 .ui 会 fail closed)。
HANDMADE: set[str] = {
    "ui_excel_merge_dialog.py",
    "ui_invoice_dialog.py",
    "ui_pdf_dialog.py",
    "ui_pdf_sort_dialog.py",
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
        # pyside6-uic 随 gui extra 的 PySide6 安装;给清晰报错。
        raise RuntimeError(
            "未找到 pyside6-uic 可执行文件。请在带 gui extra 的环境运行:"
            " uv run --all-extras python scripts/regen_ui.py"
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
    # uic 当前会在文件末尾写入一个额外空行，统一为单个换行，避免新生成文件
    # 触发 `git diff --check` 的 blank line at EOF；内容仍完全由 .ui 再生。
    generated = output_path.read_text(encoding="utf-8")
    output_path.write_text(generated.rstrip() + "\n", encoding="utf-8")


def _classification_errors() -> list[str]:
    """校验 UI_SOURCES/HANDMADE 与磁盘状态构成的分类完整性(fail closed)。

    返回错误消息列表;空列表表示登记一致。--check 与再生成都会先调用本函数,
    存在错误时不写盘、不覆盖任何文件(手写文件永不被「出现 .ui」自动接管)。
    注意:「真生成物缺失」不算分类错误——那是 regen 可修复的漂移,由
    cmd_check 报告、cmd_regen 重建。
    """
    errors: list[str] = []

    # 重复登记:同一 ui_module / ui_file 只能登记一次。
    for label, values in (
        ("ui_module", [m.ui_module for m in UI_SOURCES]),
        ("ui_file", [m.ui_file for m in UI_SOURCES]),
    ):
        for value, count in Counter(values).items():
            if count > 1:
                errors.append(f"重复登记: {label} {value} 在 UI_SOURCES 中出现 {count} 次")

    # 交叉登记:同一模块不能既走 uic 再生又在 HANDMADE。
    for module in sorted({m.ui_module for m in UI_SOURCES} & HANDMADE):
        errors.append(f"交叉登记: {module} 同时在 UI_SOURCES 与 HANDMADE 中,必须二选一")

    # 已登记源丢失:UI_SOURCES 声明的 .ui 必须真实存在于 forms/。
    for m in UI_SOURCES:
        if not (_FORMS_DIR / m.ui_file).is_file():
            errors.append(
                f"已登记源丢失: forms/{m.ui_file} 不存在(generated/{m.ui_module} 声明由它生成)"
            )

    # 孤儿 .ui:forms/ 下每个 .ui 都必须被 UI_SOURCES 引用。
    # 这也是「不得因出现 .ui 自动覆盖手写」的闸门:为手写模块补 .ui 而
    # 不更新登记时,regen/check 在这里失败,不会静默接管手写文件。
    registered_files = {m.ui_file for m in UI_SOURCES}
    for p in sorted(_FORMS_DIR.glob("*.ui")):
        if p.name not in registered_files:
            errors.append(
                f"孤儿 .ui: forms/{p.name} 未被 UI_SOURCES 登记引用;"
                "新增 .ui 不会自动接管任何手写文件,请先更新 scripts/regen_ui.py 登记"
            )

    # 未登记 ui_*.py:generated/ 下每个 ui_*.py 必须归属 UI_SOURCES 或 HANDMADE。
    registered_modules = {m.ui_module for m in UI_SOURCES} | HANDMADE
    for p in sorted(_GENERATED_DIR.glob("ui_*.py")):
        if p.name not in registered_modules:
            errors.append(
                f"未登记模块: generated/{p.name} 不在 UI_SOURCES/HANDMADE 中,必须显式登记来源"
            )

    # 手写源缺失:HANDMADE 声明的文件必须存在(regen 无法重建手写源)。
    for module in sorted(HANDMADE):
        if not (_GENERATED_DIR / module).is_file():
            errors.append(
                f"手写源缺失: generated/{module} 在 HANDMADE 中但文件不存在,"
                "请从 git 历史恢复,不能用 uic 输出顶替"
            )

    return errors


def _print_errors(errors: list[str]) -> None:
    """把分类错误逐条打印到 stderr(fail closed 的统一出口)。"""
    print(f"登记分类错误({len(errors)} 项),fail closed,不写盘:", file=sys.stderr)
    for e in errors:
        print(f"  错误: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------


def cmd_regen() -> int:
    """正向再生成:对每个 UI_SOURCES 映射跑 pyside6-uic 写出对应 ui_*.py。

    先做分类完整性校验,失败则 exit 1 且不写盘(手写文件永不被自动覆盖);
    正常情况下可重建缺失的生成目标。HANDMADE 手写源不参与,只提示存在。
    """
    errors = _classification_errors()
    if errors:
        _print_errors(errors)
        return 1

    written: list[str] = []
    for m in UI_SOURCES:
        out = _GENERATED_DIR / m.ui_module
        action = "重建" if not out.is_file() else "再生成"
        _run_uic(_FORMS_DIR / m.ui_file, out)
        written.append(f"  {m.ui_file} → generated/{m.ui_module}({action})")

    if written:
        print(f"已再生成真生成物(UI_SOURCES,{len(written)} 个):")
        print("\n".join(written))
    if HANDMADE:
        print(f"HANDMADE 手写源({len(HANDMADE)} 个)未参与再生成,保持原样:")
        print("\n".join(f"  generated/{module}" for module in sorted(HANDMADE)))
    return 0


def cmd_check() -> int:
    """漂移 + 登记检测:不写盘,用于 CI。

    1. 分类完整性(缺失源/孤儿 .ui/未登记模块/重复/交叉登记)→ exit 1。
    2. 生成物缺失(UI_SOURCES 目标文件不存在)→ exit 1。
    3. 逐映射用 pyside6-uic 生成到临时文件,比对 AST 规范化结果,
       不一致 → exit 1。HANDMADE 手写源只校验存在性,不做 uic 比对。
    """
    errors = _classification_errors()
    if errors:
        _print_errors(errors)
        return 1

    drift_count = 0
    checked: list[str] = []
    for m in UI_SOURCES:
        out_path = _GENERATED_DIR / m.ui_module
        if not out_path.is_file():
            print(f"错误: 生成物缺失 generated/{m.ui_module}", file=sys.stderr)
            drift_count += 1
            continue
        # uic 生成到临时文件,读文本后即删
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_uic(_FORMS_DIR / m.ui_file, tmp_path)
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
                "  运行 `uv run --all-extras python scripts/regen_ui.py` 再生成,"
                "或确认改动为有意为之后更新 .ui。",
                file=sys.stderr,
            )
        else:
            checked.append(f"  generated/{m.ui_module} ✓")

    if checked:
        print(f"漂移检测通过(真生成物 {len(checked)} 个):")
        print("\n".join(checked))
    if HANDMADE:
        print(f"HANDMADE 手写源({len(HANDMADE)} 个,只校验存在,不比对):")
        print("\n".join(f"  generated/{module} ✓" for module in sorted(HANDMADE)))

    if drift_count > 0:
        print(f"\n失败: {drift_count} 个真生成物缺失或存在 UI 漂移。", file=sys.stderr)
        return 1
    print("\n全部通过: 登记完整,无 UI 漂移。")
    return 0


def cmd_list() -> int:
    """列出登记清单:UI_SOURCES 真生成物与 HANDMADE 手写源(便于人工核对)。"""
    errors = _classification_errors()
    print("UI 来源登记清单:")
    print(f"  forms 目录: {_FORMS_DIR}")
    print(f"  生成目录:   {_GENERATED_DIR}")
    print()
    print(f"{'ui_*.py':<28} {'来源':<10} .ui 源")
    print("-" * 72)
    for m in UI_SOURCES:
        print(f"  {m.ui_module:<26} {'uic 再生':<10} {m.ui_file}")
    for module in sorted(HANDMADE):
        print(f"  {module:<26} {'手维护':<10} (HANDMADE,无 .ui)")
    print()
    print(f"共 {len(UI_SOURCES)} 个真生成物 + {len(HANDMADE)} 个手写源。")
    if errors:
        print()
        _print_errors(errors)
        return 1
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="regen_ui.py",
        description="UI 来源登记 + 再生成 + 漂移检测(.ui → ui_*.py via pyside6-uic)。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="漂移+登记检测:不写盘,比对 uic 输出与已提交 ui_*.py,fail closed(CI 用)。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出登记清单:UI_SOURCES 真生成物 + HANDMADE 手写源。",
    )
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()
    if args.list:
        return cmd_list()
    return cmd_regen()


if __name__ == "__main__":
    raise SystemExit(main())
