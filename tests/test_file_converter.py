"""FileConverterService 公共方法的单元测试。

`_convert_legacy_format` 标注 `# pragma: no cover`(真 COM 路径),但三个公共包装
(convert_doc_to_docx / convert_xls_to_xlsx / auto_convert_if_needed)与
cleanup_temp_files / close / __del__ 可测。

策略:
- 非 Windows 平台路径(直接返回失败)— 本机 win32 不走,需 mock sys.platform。
- 包装方法构造 _LegacySpec 后委托 _convert_legacy_format;后者整体 pragma,
  但包装方法自身行(Spec 构造 + return)会执行到委托点。
- auto_convert_if_needed 按后缀路由(doc→doc_to_docx, xls→xls_to_xlsx, else 不转换)。
- cleanup_temp_files 覆盖:正常删除 / 锁定重试 / 异常静默 / 解释器关闭早退。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_toolbox.core.batch_replace.file_converter import FileConverterService

# ---------------------------------------------------------------------------
# is_conversion_needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("a.doc", True),
        ("a.DOC", True),
        ("a.xls", True),
        ("a.xlsx", False),
        ("a.docx", False),
        ("a.txt", False),
        ("a", False),
    ],
)
def test_is_conversion_needed(name: str, expected: bool):
    svc = FileConverterService()
    assert svc.is_conversion_needed(Path(name)) is expected


# ---------------------------------------------------------------------------
# convert_doc_to_docx / convert_xls_to_xlsx:委托点
# 用 mock 替换 _convert_legacy_format,验证 Spec 正确构造与透传。
# ---------------------------------------------------------------------------


def test_convert_doc_to_docx_delegates_with_word_spec(monkeypatch):
    """doc→docx:委托 _convert_legacy_format,Spec 用 Word.Application / .docx / fmt=16。"""
    svc = FileConverterService()
    captured: dict = {}

    def fake_convert(src, spec, output_path=None):
        captured["spec"] = spec
        captured["src"] = src
        captured["output_path"] = output_path
        return True, Path("out.docx"), ""

    monkeypatch.setattr(svc, "_convert_legacy_format", fake_convert)
    ok, out, err = svc.convert_doc_to_docx(Path("in.doc"))

    assert ok is True
    assert out == Path("out.docx")
    assert err == ""
    assert captured["src"] == Path("in.doc")
    spec = captured["spec"]
    assert spec.prog_id == "Word.Application"
    assert spec.new_suffix == ".docx"
    assert spec.file_format == 16
    assert spec.error_label == "doc→docx"
    # open_doc/save_doc 可调用且不崩
    app = MagicMock()
    spec.open_doc(app, "p")
    doc = MagicMock()
    spec.save_doc(doc, "p", 16)


def test_convert_doc_to_docx_passes_output_path(monkeypatch):
    """显式 output_path 透传给 _convert_legacy_format。"""
    svc = FileConverterService()
    captured: dict = {}

    def fake_convert(src, spec, output_path=None):
        captured["output_path"] = output_path
        return True, Path("x"), ""

    monkeypatch.setattr(svc, "_convert_legacy_format", fake_convert)
    svc.convert_doc_to_docx(Path("in.doc"), output_path=Path("custom.docx"))
    assert captured["output_path"] == Path("custom.docx")


def test_convert_xls_to_xlsx_delegates_with_excel_spec(monkeypatch):
    """xls→xlsx:Spec 用 Excel.Application / .xlsx / fmt=51。"""
    svc = FileConverterService()
    captured: dict = {}

    def fake_convert(src, spec, output_path=None):
        captured["spec"] = spec
        return True, Path("out.xlsx"), ""

    monkeypatch.setattr(svc, "_convert_legacy_format", fake_convert)
    ok, out, err = svc.convert_xls_to_xlsx(Path("in.xls"))

    assert ok is True and out == Path("out.xlsx") and err == ""
    spec = captured["spec"]
    assert spec.prog_id == "Excel.Application"
    assert spec.new_suffix == ".xlsx"
    assert spec.file_format == 51
    assert spec.error_label == "xls→xlsx"
    app = MagicMock()
    spec.open_doc(app, "p")
    wb = MagicMock()
    spec.save_doc(wb, "p", 51)


# ---------------------------------------------------------------------------
# auto_convert_if_needed:按后缀路由
# ---------------------------------------------------------------------------


def test_auto_convert_doc_routes_to_docx(monkeypatch):
    svc = FileConverterService()
    monkeypatch.setattr(svc, "convert_doc_to_docx", lambda p: (True, Path("x.docx"), ""))
    ok, out, err = svc.auto_convert_if_needed(Path("a.doc"))
    assert (ok, out, err) == (True, Path("x.docx"), "")


def test_auto_convert_xls_routes_to_xlsx(monkeypatch):
    svc = FileConverterService()
    monkeypatch.setattr(svc, "convert_xls_to_xlsx", lambda p: (True, Path("x.xlsx"), ""))
    ok, out, err = svc.auto_convert_if_needed(Path("a.xls"))
    assert (ok, out, err) == (True, Path("x.xlsx"), "")


def test_auto_convert_other_suffix_no_conversion():
    """非 .doc/.xls → 不需要转换,原路径返回成功。"""
    svc = FileConverterService()
    ok, out, err = svc.auto_convert_if_needed(Path("a.docx"))
    assert (ok, out, err) == (True, Path("a.docx"), "")


# ---------------------------------------------------------------------------
# cleanup_temp_files / close
# ---------------------------------------------------------------------------


def test_cleanup_temp_files_deletes_existing(tmp_path):
    """存在的临时文件被删除,temp_files 清空。"""
    svc = FileConverterService()
    f1 = tmp_path / "t1.docx"
    f2 = tmp_path / "t2.xlsx"
    f1.write_text("x")
    f2.write_text("y")
    svc.temp_files = [f1, f2]

    svc.cleanup_temp_files()

    assert not f1.exists()
    assert not f2.exists()
    assert svc.temp_files == []


def test_cleanup_temp_files_skips_missing(tmp_path):
    """不存在的文件不报错。"""
    svc = FileConverterService()
    missing = tmp_path / "gone.docx"
    svc.temp_files = [missing]

    svc.cleanup_temp_files()  # 不应抛异常

    assert svc.temp_files == []


def test_cleanup_temp_files_permission_error_retries(tmp_path, monkeypatch):
    """PermissionError 时重试最多 max_attempts(2)次;最终仍失败则跳过不抛。"""
    svc = FileConverterService()
    f = tmp_path / "locked.docx"
    f.write_text("x")
    svc.temp_files = [f]

    call_count = {"n": 0}
    real_unlink = Path.unlink

    def raising_unlink(self, *args, **kwargs):
        call_count["n"] += 1
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", raising_unlink)
    svc.cleanup_temp_files()  # 不应抛

    # 2 次尝试(0 和 1,attempt < max_attempts-1=1 → 第 0 次 continue,第 1 次 break)
    assert call_count["n"] == 2
    assert svc.temp_files == []

    # 恢复并清理
    monkeypatch.setattr(Path, "unlink", real_unlink)
    f.unlink(missing_ok=True)


def test_cleanup_temp_files_generic_exception_swallowed(tmp_path, monkeypatch):
    """非 PermissionError 异常被静默吞掉,不抛出。"""
    svc = FileConverterService()
    f = tmp_path / "bad.docx"
    f.write_text("x")
    svc.temp_files = [f]

    def raising_unlink(self, *args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(Path, "unlink", raising_unlink)
    svc.cleanup_temp_files()  # 不应抛
    assert svc.temp_files == []


def test_close_calls_cleanup(tmp_path):
    """close() 等价于 cleanup_temp_files。"""
    svc = FileConverterService()
    f = tmp_path / "t.docx"
    f.write_text("x")
    svc.temp_files = [f]

    svc.close()

    assert not f.exists()
    assert svc.temp_files == []


def test_del_does_nothing():
    """__del__ 是空实现,不应抛异常。"""
    svc = FileConverterService()
    # 直接调用 __del__ 验证不抛
    svc.__del__()


# ---------------------------------------------------------------------------
# cleanup_temp_files:解释器关闭早退分支(#pragma 难触发的防御路径)
# cleanup_temp_files 内部 `import sys`(已缓存),故注入伪造 sys 到 sys.modules
# 使内置 import 拿到我们的桩。
# ---------------------------------------------------------------------------


def _install_fake_sys(monkeypatch, fake_sys):
    """让 `import sys` 返回 fake_sys(通过 sys.modules 注入)。"""
    import sys as real_sys

    monkeypatch.setitem(real_sys.modules, "sys", fake_sys)


def test_cleanup_temp_files_early_return_when_sys_modules_lookup_falsy(monkeypatch):
    """sys.modules.get('sys') 返回假值 → 提前 return,不清理。"""
    svc = FileConverterService()
    svc.temp_files = [Path("nope.docx")]

    fake_sys = MagicMock()
    # hasattr(sys, "modules") 为 True(MagicMock 默认有),但 modules.get("sys") 返回 None
    fake_sys.modules.get.return_value = None
    _install_fake_sys(monkeypatch, fake_sys)

    svc.cleanup_temp_files()
    # 早退 → temp_files 未被 clear
    assert svc.temp_files == [Path("nope.docx")]


def test_cleanup_temp_files_swallows_exception_in_guard(monkeypatch):
    """guard 内 sys.modules 访问抛异常 → except: return(不抛出,不清理)。"""
    svc = FileConverterService()
    svc.temp_files = [Path("nope.docx")]

    fake_sys = MagicMock()
    # hasattr(sys, "modules") 在 MagicMock 上为 True;访问 .modules 抛异常触发 except
    type(fake_sys).modules = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    _install_fake_sys(monkeypatch, fake_sys)

    svc.cleanup_temp_files()  # 不应抛
    assert svc.temp_files == [Path("nope.docx")]
