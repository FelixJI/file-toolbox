"""scripts/regen_ui.py 的逻辑与契约测试。

覆盖:
  - `_normalize_ast` 的归一行为(u 前缀、unicode 转义、object 基类)。
  - `--check` fail closed:已登记源丢失、生成物缺失、漂移、未登记 ui_*.py、
    孤儿 .ui、重复/交叉登记 → exit 1;登记完整且一致 → exit 0。
  - HANDMADE 手写源:不参与 uic 比对(只有 HANDMADE 时 --check 通过);
    出现未登记 .ui 时 regen 拒绝写盘、不覆盖手写文件。
  - regen 可重建缺失的生成目标。
  - UI_SOURCES/HANDMADE 清单与真实仓库状态一致(4 真生成 + 6 手写)。
  - pyproject 工具豁免集合与 UI_SOURCES 一致(仅豁免 4 个真生成物)。

用 monkeypatch 把脚本模块的目录常量重定向到 tmp_path,构造受控的 .ui / ui_*.py,
从而不触碰真实仓库文件、也不依赖真实 pyside6-uic 的输出格式细节(对一致用例,
我们直接把「uic 输出」写成与提交文件相同;对漂移用例,写成不同)。
"""

from __future__ import annotations

import sys
import tomllib
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
# --check / --regen(用 monkeypatch 重定向目录常量到 tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 regen_ui 的目录常量重定向到 tmp_path 下的受控布局。

    返回 (forms_dir, generated_dir, install_mapping) 供测试构造场景。
    """
    forms = tmp_path / "forms"
    generated = tmp_path / "generated"
    forms.mkdir()
    generated.mkdir()
    monkeypatch.setattr(regen, "_FORMS_DIR", forms)
    monkeypatch.setattr(regen, "_GENERATED_DIR", generated)

    def install_mapping(*modules: tuple[str, str]) -> None:
        """临时把 UI_SOURCES 设为给定映射,并清空 HANDMADE。"""
        monkeypatch.setattr(
            regen, "UI_SOURCES", [regen.UiMapping(ui_module=m, ui_file=f) for m, f in modules]
        )
        monkeypatch.setattr(regen, "HANDMADE", set())

    return forms, generated, install_mapping


class TestCheckConsistent:
    def test_check_passes_when_consistent(self, isolated_layout, capsys, monkeypatch):
        """登记完整、有 .ui 且 uic 输出与提交文件 AST 规范化一致 → exit 0。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
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
        install_mapping(("ui_foo.py", "foo.ui"))
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

    def test_check_fails_on_missing_generated_target(self, isolated_layout, capsys, monkeypatch):
        """已登记映射的生成物文件缺失 → exit 1(fail closed,不再「无源即通过」)。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")
        # 故意不创建 generated/ui_foo.py

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("目标缺失时应先报错,不应跑到 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "生成物缺失" in err


class TestCheckRegistrationFailClosed:
    """登记分类不完整时 --check 直接失败(fail closed,不再跳过缺失源)。"""

    def test_check_fails_when_registered_ui_missing(self, isolated_layout, capsys, monkeypatch):
        """旧契约「无 .ui 时 --check 直接通过」是错误的:已登记源丢失必须 exit 1。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        # forms 下没有 foo.ui,但映射已登记
        (generated / "ui_foo.py").write_text("class Ui_Foo:\n    pass\n", encoding="utf-8")

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("源缺失时不应触发 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "已登记源丢失" in err

    def test_check_fails_on_unregistered_generated_module(self, isolated_layout, capsys):
        """generated/ 下出现未登记的 ui_*.py → exit 1。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")
        (generated / "ui_foo.py").write_text("class Ui_Foo:\n    pass\n", encoding="utf-8")
        (generated / "ui_stray.py").write_text("class Ui_Stray:\n    pass\n", encoding="utf-8")

        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "未登记模块" in err and "ui_stray.py" in err

    def test_check_fails_on_orphan_ui(self, isolated_layout, capsys):
        """forms/ 下出现未被 UI_SOURCES 登记的孤儿 .ui → exit 1。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")
        (forms / "stray.ui").write_text("<ui/>", encoding="utf-8")
        (generated / "ui_foo.py").write_text("class Ui_Foo:\n    pass\n", encoding="utf-8")

        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "孤儿 .ui" in err and "stray.ui" in err

    def test_check_fails_on_cross_registration(self, isolated_layout, capsys, monkeypatch):
        """同一模块同时在 UI_SOURCES 与 HANDMADE → exit 1(交叉登记)。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_hand.py", "hand.ui"))
        monkeypatch.setattr(regen, "HANDMADE", {"ui_hand.py"})
        (forms / "hand.ui").write_text("<ui/>", encoding="utf-8")
        (generated / "ui_hand.py").write_text("class Ui_Hand:\n    pass\n", encoding="utf-8")

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("分类不完整时不应触发 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "交叉登记" in err

    @pytest.mark.parametrize(
        ("mapping_a", "mapping_b", "label"),
        [
            (("ui_foo.py", "a.ui"), ("ui_foo.py", "b.ui"), "ui_module"),
            (("ui_foo.py", "same.ui"), ("ui_bar.py", "same.ui"), "ui_file"),
        ],
    )
    def test_check_fails_on_duplicate_registration(
        self, isolated_layout, capsys, monkeypatch, mapping_a, mapping_b, label
    ):
        """UI_SOURCES 中重复登记同一 ui_module / ui_file → exit 1。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(mapping_a, mapping_b)
        for _, ui_file in (mapping_a, mapping_b):
            (forms / ui_file).write_text("<ui/>", encoding="utf-8")
        for module, _ in (mapping_a, mapping_b):
            (generated / module).write_text("class Ui_X:\n    pass\n", encoding="utf-8")

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("分类不完整时不应触发 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "重复登记" in err and label in err

    def test_check_fails_when_handmade_file_missing(self, isolated_layout, capsys, monkeypatch):
        """HANDMADE 声明的手写文件不存在 → exit 1(regen 无法重建手写源)。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping()
        monkeypatch.setattr(regen, "HANDMADE", {"ui_lost.py"})
        # generated/ui_lost.py 不存在

        rc = regen.cmd_check()
        err = capsys.readouterr().err
        assert rc == 1
        assert "手写源缺失" in err


class TestCheckHandmadeSkipped:
    def test_check_passes_with_only_handmade(self, isolated_layout, capsys, monkeypatch):
        """无 UI_SOURCES 映射时,HANDMADE 模块只做存在性校验,不参与 uic 比对。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping()
        monkeypatch.setattr(regen, "HANDMADE", {"ui_hand.py"})
        (generated / "ui_hand.py").write_text("class Ui_Hand:\n    pass\n", encoding="utf-8")

        # 若误把手维护项送进 uic,会触发 boom
        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("HANDMADE 模块不应触发 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_check()
        out = capsys.readouterr().out
        assert rc == 0
        assert "手写源" in out and "ui_hand.py" in out


class TestRegenGuard:
    """cmd_regen 先验证完整分类,不因出现 .ui 自动覆盖手写。"""

    def test_regen_rebuilds_missing_generated_target(self, isolated_layout, capsys, monkeypatch):
        """登记完整时,正常 regen 可重建缺失的生成目标。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")
        # generated/ui_foo.py 缺失

        uic_output = "class Ui_Foo:\n    pass\n"

        def fake_run_uic(ui_path: Path, output_path: Path) -> None:
            output_path.write_text(uic_output, encoding="utf-8")

        monkeypatch.setattr(regen, "_run_uic", fake_run_uic)
        rc = regen.cmd_regen()
        out = capsys.readouterr().out
        assert rc == 0
        assert (generated / "ui_foo.py").read_text(encoding="utf-8") == uic_output
        assert "重建" in out

    def test_regen_does_not_overwrite_handmade_when_ui_appears(
        self, isolated_layout, capsys, monkeypatch
    ):
        """出现未登记 .ui(指向手写模块)时 regen fail closed,不改写手写文件。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        monkeypatch.setattr(regen, "HANDMADE", {"ui_hand.py"})

        (forms / "foo.ui").write_text("<ui/>", encoding="utf-8")
        # 有人为手写模块补了 .ui 却没更新登记 → 孤儿 .ui
        (forms / "handmade.ui").write_text("<ui/>", encoding="utf-8")

        sentinel = "# 手写内容 SENTINEL\n"
        (generated / "ui_foo.py").write_text("class Ui_Foo:\n    pass\n", encoding="utf-8")
        (generated / "ui_hand.py").write_text(sentinel, encoding="utf-8")

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("分类不完整时 regen 不应调用 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_regen()
        err = capsys.readouterr().err
        assert rc == 1
        assert "孤儿 .ui" in err and "handmade.ui" in err
        assert (generated / "ui_hand.py").read_text(encoding="utf-8") == sentinel

    def test_regen_refuses_when_classification_broken(self, isolated_layout, capsys, monkeypatch):
        """登记源丢失等分类错误时 regen 拒绝写盘,已提交内容保持原样。"""
        forms, generated, install_mapping = isolated_layout
        install_mapping(("ui_foo.py", "foo.ui"))
        # forms 下没有 foo.ui → 已登记源丢失
        committed = "class Ui_Foo:\n    pass\n"
        (generated / "ui_foo.py").write_text(committed, encoding="utf-8")

        def boom(ui_path: Path, output_path: Path) -> None:
            raise AssertionError("分类不完整时 regen 不应调用 uic")

        monkeypatch.setattr(regen, "_run_uic", boom)
        rc = regen.cmd_regen()
        err = capsys.readouterr().err
        assert rc == 1
        assert "已登记源丢失" in err
        assert (generated / "ui_foo.py").read_text(encoding="utf-8") == committed


class TestCmdList:
    def test_cmd_list_reports_full_registry_on_real_repo(self, capsys):
        """--list 准确列出 4 个真生成物 + 6 个手写源,且真实仓库登记有效。"""
        rc = regen.cmd_list()
        out = capsys.readouterr().out
        assert rc == 0
        for m in UI_SOURCES:
            assert m.ui_module in out
            assert m.ui_file in out
            assert "uic 再生" in out
        for module in HANDMADE:
            assert module in out
            assert "手维护" in out
        assert f"共 {len(UI_SOURCES)} 个真生成物 + {len(HANDMADE)} 个手写源" in out


# ---------------------------------------------------------------------------
# HANDMADE / UI_SOURCES 清单完整性(对真实仓库)
# ---------------------------------------------------------------------------


class TestRegistryIntegrity:
    """UI_SOURCES/HANDMADE 登记与真实仓库状态一致。"""

    def test_real_repo_classification_is_valid(self):
        """真实仓库通过分类完整性校验(无缺失/孤儿/未登记/重复/交叉)。"""
        assert regen._classification_errors() == []

    def test_registry_covers_all_generated_ui_modules(self):
        """4 + 6 登记恰好覆盖 generated/ 下全部 ui_*.py,无遗漏无多余。"""
        registered = {m.ui_module for m in UI_SOURCES} | HANDMADE
        actual = {p.name for p in _GENERATED_DIR.glob("ui_*.py")}
        assert actual == registered

    def test_handmade_files_exist_in_generated(self):
        """清单中的每个 ui_*.py 必须真实存在于 generated/。"""
        for module in HANDMADE:
            assert (_GENERATED_DIR / module).is_file(), (
                f"HANDMADE 列表里的 {module} 在 generated/ 下不存在"
            )

    def test_true_generated_have_ui_sources(self):
        """UI_SOURCES(真生成)与 HANDMADE(手写)不得交叉,且每个真生成有 .ui。"""
        assert not ({m.ui_module for m in UI_SOURCES} & HANDMADE)
        forms_dir = _REPO_ROOT / "file_toolbox" / "gui" / "forms"
        for m in UI_SOURCES:
            assert (forms_dir / m.ui_file).is_file(), (
                f"UI_SOURCES 里的 {m.ui_file} 在 forms/ 下不存在"
            )

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


class TestToolExemptions:
    """pyproject 工具豁免集合与 UI_SOURCES(4 个真生成物)严格一致。"""

    @staticmethod
    def _pyproject() -> dict:
        return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_ruff_exclude_matches_true_generated_set(self):
        data = self._pyproject()["tool"]["ruff"]
        expected = {f"file_toolbox/gui/generated/{m.ui_module}" for m in UI_SOURCES}
        assert set(data.get("exclude", [])) == expected

    def test_ruff_has_no_whole_directory_generated_exemptions(self):
        data = self._pyproject()["tool"]["ruff"]
        per_file = data["lint"].get("per-file-ignores", {})
        assert not any(key.startswith("file_toolbox/gui/generated") for key in per_file)
        assert not any(entry == "file_toolbox/gui/generated" for entry in data.get("exclude", []))

    def test_mypy_override_matches_true_generated_set(self):
        overrides = self._pyproject()["tool"]["mypy"]["overrides"]
        ignore_error_overrides = [o for o in overrides if o.get("ignore_errors")]
        assert len(ignore_error_overrides) == 1
        expected = {f"file_toolbox.gui.generated.{m.ui_module[:-3]}" for m in UI_SOURCES}
        assert set(ignore_error_overrides[0]["module"]) == expected
        # generated 包不得再享受整目录通配豁免(手写文件按普通规则检查)
        assert not any(
            module.startswith("file_toolbox.gui.generated") and "*" in module
            for o in overrides
            for module in o.get("module", [])
        )
