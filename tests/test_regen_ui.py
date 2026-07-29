"""scripts/regen_ui.py 的逻辑测试。

覆盖:
  - `_normalize_ast` 的归一行为(u 前缀、unicode 转义、object 基类)。
  - `--check` 三态:无 .ui 时通过;有 .ui 且一致时通过;有 .ui 但漂移时 exit 1。
  - HANDMADE 清单完整性:清单中的文件确实存在于 generated/,且无 .ui(否则应移出)。
  - UI_SOURCES 映射:每个 ui_module 在 generated/ 下存在。

用 monkeypatch 把脚本模块的目录常量重定向到 tmp_path,构造受控的 .ui / ui_*.py,
从而不触碰真实仓库文件、也不依赖真实 pyside6-uic 的输出格式细节(对一致用例,
我们直接把「uic 输出」写成与提交文件相同;对漂移用例,写成不同)。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 tests 能 import scripts 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.regen_ui as regen  # noqa: E402
from scripts.regen_ui import (  # noqa: E402
    HANDMADE,
    UI_SOURCES,
    _normalize_ast,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GENERATED_DIR = _REPO_ROOT / "file_toolbox" / "gui" / "generated"


# ---------------------------------------------------------------------------
# _normalize_ast
# ---------------------------------------------------------------------------


class TestNormalizeAst:
    """AST 规范化应抹去 pyside6-uic 与人工文件之间的纯表面差异。"""

    def test_strips_object_base_class(self):
        a = "class Ui_X(object):\n    pass\n"
        b = "class Ui_X:\n    pass\n"
        assert _normalize_ast(a) == _normalize_ast(b)

    def test_strips_u_string_prefix(self):
        # uic 输出 u"...",人工文件 "..."。值相同应归一。
        a = 'x = u"hi"\n'
        b = 'x = "hi"\n'
        assert _normalize_ast(a) == _normalize_ast(b)

    def test_equates_unicode_escape_and_literal(self):
        # uic 输出 \uXXXX 转义,人工文件用原字面。二者解析为同一字符串。
        a = 'x = "\\u4f60\\u597d"\n'
        b = 'x = "你好"\n'
        assert _normalize_ast(a) == _normalize_ast(b)

    def test_detects_real_drift(self):
        a = 'x = "你好"\n'
        b = 'x = "再见"\n'
        assert _normalize_ast(a) != _normalize_ast(b)

    def test_normalizes_import_style(self):
        # 单行 vs 多行 import 等价
        a = "from X import A, B\nA\nB\n"
        b = "from X import (\n    A,\n    B,\n)\nA\nB\n"
        assert _normalize_ast(a) == _normalize_ast(b)


# ---------------------------------------------------------------------------
# --check 三态(用 monkeypatch 重定向目录常量到 tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 regen_ui 的目录常量与 _run_uic 重定向到 tmp_path 下的受控布局。

    返回 (forms_dir, generated_dir, mapping_factory) 供测试构造场景。
    """
    forms = tmp_path / "forms"
    generated = tmp_path / "generated"
    forms.mkdir()
    generated.mkdir()
    monkeypatch.setattr(regen, "_FORMS_DIR", forms)
    monkeypatch.setattr(regen, "_GENERATED_DIR", generated)

    def install_mapping(module: str, ui_file: str) -> None:
        """临时把 UI_SOURCES 设为单个映射,并清空 HANDMADE。"""
        m = regen.UiMapping(ui_module=module, ui_file=ui_file)
        monkeypatch.setattr(regen, "UI_SOURCES", [m])
        monkeypatch.setattr(regen, "HANDMADE", set())

    return forms, generated, install_mapping


class TestCheckNoUi:
    def test_check_passes_when_no_ui(self, isolated_layout, capsys, monkeypatch):
        """无 .ui 时 --check 直接通过(建立链路、待后续补 .ui)。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping("ui_foo.py", "foo.ui")
        # generated 下有 ui_foo.py,但 forms 下没有 foo.ui
        (generated / "ui_foo.py").write_text("class Ui_Foo:\n    pass\n", encoding="utf-8")
        # _run_uic 不应被调用(无 .ui)
        rc = regen.cmd_check()
        out = capsys.readouterr().out
        assert rc == 0
        assert "跳过漂移检测" in out


class TestCheckConsistent:
    def test_check_passes_when_consistent(self, isolated_layout, capsys, monkeypatch):
        """有 .ui 且 uic 输出与提交文件 AST 规范化一致 → exit 0。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping("ui_foo.py", "foo.ui")
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")

        uic_output = (
            "from PySide6.QtWidgets import QLabel\n"
            "class Ui_Foo(object):\n"
            "    def retranslateUi(self, F):\n"
            '        F.setWindowTitle(QCoreApplication.translate("F", u"\\u4f60\\u597d", None))\n'
            "    # retranslateUi\n"
        )
        committed = (
            "from PySide6.QtWidgets import QLabel\n"
            "class Ui_Foo:\n"
            "    def retranslateUi(self, F):\n"
            '        F.setWindowTitle(QCoreApplication.translate("F", "你好", None))\n'
            "    # retranslateUi\n"
        )
        (generated / "ui_foo.py").write_text(committed, encoding="utf-8")

        def fake_run_uic(ui_path: Path, output_path: Path) -> None:
            output_path.write_text(uic_output, encoding="utf-8")

        monkeypatch.setattr(regen, "_run_uic", fake_run_uic)
        rc = regen.cmd_check()
        out = capsys.readouterr().out
        assert rc == 0
        assert "通过" in out


class TestCheckDrift:
    def test_check_fails_on_drift(self, isolated_layout, capsys, monkeypatch):
        """有 .ui 但 uic 输出与提交文件不一致 → exit 1,打印漂移。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping("ui_foo.py", "foo.ui")
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")

        uic_output = (
            "class Ui_Foo:\n"
            "    def retranslateUi(self, F):\n"
            '        F.setWindowTitle(QCoreApplication.translate("F", "新标题", None))\n'
            "    # retranslateUi\n"
        )
        committed = (
            "class Ui_Foo:\n"
            "    def retranslateUi(self, F):\n"
            '        F.setWindowTitle(QCoreApplication.translate("F", "旧标题", None))\n'
            "    # retranslateUi\n"
        )
        (generated / "ui_foo.py").write_text(committed, encoding="utf-8")

        def fake_run_uic(ui_path: Path, output_path: Path) -> None:
            output_path.write_text(uic_output, encoding="utf-8")

        monkeypatch.setattr(regen, "_run_uic", fake_run_uic)
        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "漂移" in err


class TestCheckHandmadeSkipped:
    def test_check_passes_with_only_handmade_no_ui(self, isolated_layout, capsys, monkeypatch):
        """HANDMADE 模块(无 .ui)不参与漂移比对;只有 HANDMADE 时 --check 通过。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping("ui_hand.py", "hand.ui")
        monkeypatch.setattr(regen, "HANDMADE", {"ui_hand.py"})
        # forms 下没有 hand.ui → 该模块按手维护,不进 _active_mappings
        (generated / "ui_hand.py").write_text("class Ui_Hand:\n    pass\n", encoding="utf-8")

        # 若误把手维护项送进 uic,会触发 boom
        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("无 .ui 的 HANDMADE 模块不应触发 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        out = capsys.readouterr().out
        assert rc == 0
        assert "跳过漂移检测" in out


# ---------------------------------------------------------------------------
# HANDMADE / UI_SOURCES 清单完整性(对真实仓库)
# ---------------------------------------------------------------------------


class TestHandmadeIntegrity:
    """HANDMADE 清单与真实仓库状态一致。"""

    def test_handmade_files_exist_in_generated(self):
        """清单中的每个 ui_*.py 必须真实存在于 generated/。"""
        for module in HANDMADE:
            assert (_GENERATED_DIR / module).is_file(), (
                f"HANDMADE 列表里的 {module} 在 generated/ 下不存在"
            )

    def test_handmade_files_have_no_ui_source(self):
        """HANDMADE 中的模块(其 .ui 在 UI_SOURCES 中声明的)目前不应有对应 .ui 文件。
        若 .ui 已补齐,应将其从 HANDMADE 移出(让 regen 接管)。"""
        forms_dir = _REPO_ROOT / "file_toolbox" / "gui" / "forms"
        module_to_ui = {m.ui_module: m.ui_file for m in UI_SOURCES}
        for module in HANDMADE:
            ui_file = module_to_ui.get(module)
            if ui_file is None:
                # 无 .ui 映射(如 invoice),天然满足
                continue
            assert not (forms_dir / ui_file).is_file(), (
                f"{module} 在 HANDMADE 中,但 forms/{ui_file} 已存在 —— "
                "应从 HANDMADE 移出使其接入 uic 再生"
            )


class TestUiSourcesIntegrity:
    """UI_SOURCES 映射表完整。"""

    def test_every_mapping_module_exists(self):
        """每个映射的 ui_module 必须存在于 generated/。"""
        for m in UI_SOURCES:
            assert (_GENERATED_DIR / m.ui_module).is_file(), (
                f"UI_SOURCES 里的 {m.ui_module} 在 generated/ 下不存在"
            )

    def test_ui_module_names_follow_convention(self):
        for m in UI_SOURCES:
            assert m.ui_module.startswith("ui_") and m.ui_module.endswith(".py")
            assert m.ui_file.endswith(".ui")
