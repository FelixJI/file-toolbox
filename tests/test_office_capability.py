"""按需能力状态查询(Issue #143)契约:三态预筛、按 kind 独立、登记消费与文案。

核心回归锚点:
- ``_probe_registry_outcome`` 把"未注册(FileNotFoundError)"与"检测错误
  (OSError)"严格区分;旧实现把 OSError 一律当 False(缺失)展示;
- 套件级缓存(``_cached_engines`` 以 Word/KWPS ProgID 判定)不能据 Word 缺失
  否定 Excel/PPT:按 kind 查询各自探测自己的 ProgID;
- 注册存在只是"检测到"预筛,不冒称真实 COM 可用;只有本进程真实 Dispatch
  成功(verified)才展示"已验证"。
"""

import builtins

import pytest

from file_toolbox.common.tool_registry import spec_by_tool_id
from file_toolbox.core.batch_pdf import engine_manager as em
from file_toolbox.core.batch_pdf.engine_manager import (
    EngineManager,
    KindAvailability,
    ProbeState,
    _probe_registry_outcome,
)
from file_toolbox.core.office_capability import (
    format_status,
    format_statuses,
    office_kind_status,
    pandoc_status,
    record_office_session_success,
    tool_capability_statuses,
)


@pytest.fixture(autouse=True)
def _reset_kind_state():
    """隔离按 kind 的类级 memo/验证集合(与套件级状态互不影响)。"""
    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}
    yield
    EngineManager._cached_kind_probes = None
    EngineManager._verified_kinds = {}


# ---------------------------------------------------------------------------
# _probe_registry_outcome:三态探测(缺失 / 检测错误 / 命中)
# ---------------------------------------------------------------------------


def test_probe_outcome_missing_vs_error(monkeypatch):
    """FileNotFoundError → 确定未注册;OSError → 检测错误(registered=None)。"""
    import winreg

    def fake_open(root, subkey, *args, **kwargs):
        if subkey.lower() == "word.application":
            return object()
        if subkey.lower() == "kwps.application":
            raise FileNotFoundError(subkey)
        raise OSError("denied")

    monkeypatch.setattr(winreg, "OpenKey", fake_open)
    monkeypatch.setattr(winreg, "CloseKey", lambda handle: None)

    assert _probe_registry_outcome("Word.Application").registered is True
    missing = _probe_registry_outcome("KWPS.Application")
    assert missing.registered is False and missing.detail == ""
    error = _probe_registry_outcome("Excel.Application")
    assert error.registered is None and "denied" in error.detail


def test_probe_bool_wrapper_keeps_legacy_semantics(monkeypatch):
    """既有 bool 视图:检测错误仍返回 False(不破坏现有消费者)。"""
    import winreg

    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert EngineManager._probe_registry("Word.Application") is False


def test_probe_outcome_non_windows_platform(monkeypatch):
    """非 Windows(winreg 不可用)→ 未注册 + 平台说明(不是检测错误)。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("simulated non-windows")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    outcome = _probe_registry_outcome("Word.Application")
    assert outcome.registered is False
    assert "Windows" in outcome.detail


# ---------------------------------------------------------------------------
# kind_availability:按 kind 独立预筛、memo、verified 证据
# ---------------------------------------------------------------------------


def _patch_outcomes(monkeypatch, table: dict[str, em._ProbeOutcome]) -> list[str]:
    probed: list[str] = []
    table = dict(table)

    def fake_outcome(prog_id: str) -> em._ProbeOutcome:
        probed.append(prog_id)
        return table[prog_id]

    monkeypatch.setattr(em, "_probe_registry_outcome", fake_outcome)
    return probed


def test_word_missing_does_not_disable_excel(monkeypatch):
    """核心回归:套件级缓存断言无 Office(Word 未注册),Excel 仍按自身 ProgID 可用。"""
    EngineManager._cached_engines = {"office": False, "wps": False}
    probed = _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(False),
            "Excel.Application": em._ProbeOutcome(True),
            "Ket.Application": em._ProbeOutcome(False),
        },
    )
    try:
        manager = EngineManager()
        assert manager.kind_availability("word").state is ProbeState.MISSING
        excel = manager.kind_availability("excel")
        assert excel.state is ProbeState.AVAILABLE
        assert excel.engine == "office"
        assert "Excel.Application" in probed  # 事实上的独立探测,不是套件结论
    finally:
        EngineManager._cached_engines = None


def test_kind_probe_error_is_not_missing(monkeypatch):
    """ms 未注册 + wps 探测 OSError → PROBE_ERROR(不得展示为"未检测到")。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(None, "denied"),
        },
    )
    availability = EngineManager().kind_availability("word")
    assert availability.state is ProbeState.PROBE_ERROR
    assert "denied" in availability.detail


def test_kind_availability_memo_and_refresh(monkeypatch):
    """进程内 memo:二次查询不重探;refresh=True 强制重探。

    memo 存双套件探测结果,选择层每次构造值相等的新对象(旧的同一对象断言
    是旧 memo 实现细节,不重探才是契约)。
    """
    probed = _patch_outcomes(
        monkeypatch,
        {"Word.Application": em._ProbeOutcome(False), "KWPS.Application": em._ProbeOutcome(True)},
    )
    manager = EngineManager()
    first = manager.kind_availability("word")
    assert first.engine == "wps"
    count = len(probed)
    second = manager.kind_availability("word")
    assert second == first  # memo 命中,值一致
    assert len(probed) == count
    manager.kind_availability("word", refresh=True)
    assert len(probed) == count + 2


def test_real_dispatch_marks_kind_verified(monkeypatch):
    """真实 Dispatch 成功 → kind 标记 verified(预筛命中与验证区分)。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(False),
            "Excel.Application": em._ProbeOutcome(True),
            "Ket.Application": em._ProbeOutcome(False),
        },
    )
    from unittest.mock import MagicMock

    import win32com.client

    dispatch = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch)
    EngineManager._cached_engines = {"office": True, "wps": False}
    try:
        manager = EngineManager()
        before = manager.kind_availability("excel")
        assert before.state is ProbeState.AVAILABLE and before.verified is False
        manager.init_excel()  # 真实 Dispatch 路径(mock DispatchEx)
        after = manager.kind_availability("excel")
        assert after.verified is True
        assert EngineManager._verified_kinds["excel"] == "office"  # 证据绑定实际套件
    finally:
        EngineManager._cached_engines = None


def test_wps_fallback_success_binds_actual_suite_not_stale_prescreen(monkeypatch, tmp_path):
    """F4 回归:MS 预筛命中但 Dispatch 回退 WPS 成功 → 引擎=WPS 的 verified。

    旧实现仅置 verified,保留 memo 的 engine=office,展示会冒称"MS Office
    已验证可用"而实际成功的是 WPS。
    """
    from unittest.mock import MagicMock

    import win32com.client

    from file_toolbox.core.batch_pdf import engine_cache

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine_cache, "save", lambda *a, **k: True)
    monkeypatch.setattr(engine_cache, "load_with_reason", lambda *a, **k: (None, "missing"))
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(True),
            "KWPS.Application": em._ProbeOutcome(False),
        },
    )
    wps_app = MagicMock()
    dispatch = MagicMock(side_effect=[RuntimeError("ms busy"), wps_app])
    monkeypatch.setattr(win32com.client, "DispatchEx", dispatch)
    EngineManager._cached_engines = {"office": True, "wps": False}
    try:
        manager = EngineManager()
        pre = manager.kind_availability("word")
        assert pre.engine == "office" and pre.verified is False
        assert manager.init_word() is wps_app  # MS 失败 → 回退 WPS 成功
        after = manager.kind_availability("word")
        assert after.state is ProbeState.AVAILABLE
        assert after.engine == "wps"  # 实际成功套件,非旧预筛
        assert after.verified is True
    finally:
        EngineManager._cached_engines = None


def test_real_dispatch_corrects_missing_and_probe_error(monkeypatch, tmp_path):
    """F4 回归:预筛 missing/probe_error 被真实 Dispatch 成功纠正为已验证可用。"""
    from unittest.mock import MagicMock

    import win32com.client

    from file_toolbox.core.batch_pdf import engine_cache

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine_cache, "save", lambda *a, **k: True)
    monkeypatch.setattr(engine_cache, "load_with_reason", lambda *a, **k: (None, "missing"))
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(None, "denied"),
        },
    )
    monkeypatch.setattr(win32com.client, "DispatchEx", MagicMock(return_value=MagicMock()))
    EngineManager._cached_engines = {"office": False, "wps": False}
    try:
        manager = EngineManager()
        pre = manager.kind_availability("word")
        assert pre.state is ProbeState.PROBE_ERROR  # wps 探测错误,未误标缺失
        manager.init_word()  # 回退循环内 Word Dispatch 成功(mock)
        after = manager.kind_availability("word")
        assert after.state is ProbeState.AVAILABLE
        assert after.engine == "office"
        assert after.verified is True
    finally:
        EngineManager._cached_engines = None


def test_kind_availability_rejects_unknown_kind():
    with pytest.raises(ValueError, match="未知的 Office 应用类别"):
        EngineManager().kind_availability("pptx")


def test_kind_availability_non_windows_detail(monkeypatch):
    """非 Windows:MISSING 且 detail 说明仅支持 Windows(不是检测错误)。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("simulated non-windows")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    availability = EngineManager().kind_availability("word")
    assert availability.state is ProbeState.MISSING
    assert "Windows" in availability.detail


# ---------------------------------------------------------------------------
# office_capability:登记消费、Pandoc、文案
# ---------------------------------------------------------------------------


def test_registry_declarations_by_tool():
    """登记声明:pdf 三类 Office、replace 两类、attendance 恒 Excel、markdown Pandoc。"""
    pdf = spec_by_tool_id("pdf")
    assert pdf is not None
    assert [need.kind for need in pdf.office_needs] == ["word", "excel", "ppt"]
    replace = spec_by_tool_id("replace")
    assert replace is not None
    assert [need.kind for need in replace.office_needs] == ["word", "excel"]
    attendance = spec_by_tool_id("attendance")
    assert attendance is not None
    assert [need.kind for need in attendance.office_needs] == ["excel"]
    markdown = spec_by_tool_id("markdown_convert")
    assert markdown is not None
    assert markdown.office_needs == () and markdown.requires_pandoc is True


def test_pure_tools_have_no_external_requirements():
    for tool_id in ("rename", "mkdir", "invoice", "excel_merge", "pdf_sort", "plan_schedule"):
        statuses = tool_capability_statuses(tool_id)
        assert statuses == [], f"{tool_id} 应为纯文件工具"
        assert format_statuses(statuses) == "纯文件处理,无需外部引擎"


def test_tool_statuses_follow_declared_needs(monkeypatch):
    monkeypatch.setattr(
        EngineManager,
        "kind_availability",
        lambda self, kind, refresh=False, engines=None: KindAvailability(
            kind, ProbeState.AVAILABLE if kind == "excel" else ProbeState.MISSING, "office"
        ),
    )
    statuses = tool_capability_statuses("attendance")
    assert [status.requirement for status in statuses] == ["Excel(xlsx)"]
    assert statuses[0].state is ProbeState.AVAILABLE
    assert statuses[0].detail == "MS Office"


def test_pandoc_status_available_and_missing():
    status = pandoc_status()
    assert status.requirement == "内置 Pandoc(docx)"
    if status.state is ProbeState.AVAILABLE:  # 本环境装有 pypandoc_binary
        assert "pandoc" in status.detail.lower()


def test_pandoc_status_missing_reports_accurate_error(monkeypatch):
    import file_toolbox.core.office_capability as capability

    def broken() -> None:
        raise ImportError("未找到内置 Pandoc: fake-path(不回退 PATH 上的 pandoc)")

    monkeypatch.setattr(capability, "locate_bundled_pandoc", broken)
    status = capability.pandoc_status()
    assert status.state is ProbeState.MISSING
    assert "不回退 PATH" in status.detail


def test_format_status_wording_distinguishes_precheck_and_verified():
    from file_toolbox.core.office_capability import CapabilityStatus

    precheck = CapabilityStatus("Word(doc/docx)", ProbeState.AVAILABLE, "MS Office")
    assert "检测到" in format_status(precheck)
    assert "已验证" not in format_status(precheck)
    verified = CapabilityStatus("Word(doc/docx)", ProbeState.AVAILABLE, "MS Office", True)
    assert "已验证可用" in format_status(verified)
    missing = CapabilityStatus("Word(doc/docx)", ProbeState.MISSING, "此功能仅支持 Windows 系统")
    assert "未检测到" in format_status(missing) and "Windows" in format_status(missing)
    errored = CapabilityStatus("Word(doc/docx)", ProbeState.PROBE_ERROR, "denied")
    assert "检测失败(denied)" in format_status(errored)


def test_format_statuses_appends_precheck_qualifier():
    from file_toolbox.core.office_capability import CapabilityStatus

    verified_only = [CapabilityStatus("Excel(xlsx)", ProbeState.AVAILABLE, "MS Office", True)]
    assert "预检结论" not in format_statuses(verified_only)
    unverified = [
        CapabilityStatus("Word(doc/docx)", ProbeState.AVAILABLE, "MS Office"),
        CapabilityStatus("内置 Pandoc(docx)", ProbeState.AVAILABLE, "fake"),
    ]
    text = format_statuses(unverified)
    assert "预检结论,实际以执行结果为准" in text
    assert "Word(doc/docx): 检测到" in text and "内置 Pandoc(docx)" in text


def test_office_kind_status_maps_availability(monkeypatch):
    monkeypatch.setattr(
        EngineManager,
        "kind_availability",
        lambda self, kind, refresh=False, engines=None: KindAvailability(kind, ProbeState.MISSING),
    )
    status = office_kind_status("ppt", (".ppt", ".pptx"))
    assert status.requirement == "PowerPoint(ppt/pptx)"
    assert status.state is ProbeState.MISSING and status.verified is False


# ---------------------------------------------------------------------------
# F7:支持套件按实际 adapter 限制——PDF 转换链有 WPS 回退,替换/考勤仅 MS
# ---------------------------------------------------------------------------


def test_registry_declares_adapter_supported_engines():
    """登记声明:pdf 各 kind 允许 MS+WPS;replace/attendance 仅 MS(与实际
    handler 的 ProgID 一致,不为修提示扩大 WPS 业务支持)。"""
    pdf = spec_by_tool_id("pdf")
    assert pdf is not None
    assert all(need.engines == ("office", "wps") for need in pdf.office_needs)
    replace = spec_by_tool_id("replace")
    assert replace is not None
    assert all(need.engines == ("office",) for need in replace.office_needs)
    attendance = spec_by_tool_id("attendance")
    assert attendance is not None
    assert all(need.engines == ("office",) for need in attendance.office_needs)


def test_office_kind_status_restricts_unsupported_suite(monkeypatch):
    """WPS-only 机器:engines 限定 MS 时不得展示为可用,pdf 语义仍可用。"""
    _patch_outcomes(
        monkeypatch,
        {"Word.Application": em._ProbeOutcome(False), "KWPS.Application": em._ProbeOutcome(True)},
    )
    ms_only = office_kind_status("word", (".doc", ".docx"), engines=("office",))
    assert ms_only.state is ProbeState.MISSING
    assert "WPS" in ms_only.detail and "仅支持" in ms_only.detail
    both = office_kind_status("word", (".doc", ".docx"), engines=("office", "wps"))
    assert both.state is ProbeState.AVAILABLE
    assert "WPS" in both.detail


def test_wps_only_machine_reports_missing_for_ms_only_tools(monkeypatch):
    """F7 回归:WPS-only 环境下 replace/attendance 能力提示必须为未检测到,
    不得把 PDF 的 MS+WPS 支持集合套用于仅 MS 的 adapter。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(True),
            "Excel.Application": em._ProbeOutcome(False),
            "Ket.Application": em._ProbeOutcome(True),
            "PowerPoint.Application": em._ProbeOutcome(False),
            "KWPP.Application": em._ProbeOutcome(False),
        },
    )
    for tool_id in ("replace", "attendance"):
        statuses = tool_capability_statuses(tool_id)
        assert statuses, tool_id
        for status in statuses:
            assert status.state is ProbeState.MISSING, f"{tool_id} 不应展示 WPS 可用"
            assert "WPS" in status.detail
    pdf_statuses = {
        status.requirement.split("(", 1)[0]: status for status in tool_capability_statuses("pdf")
    }
    assert pdf_statuses["Word"].state is ProbeState.AVAILABLE
    assert pdf_statuses["Excel"].state is ProbeState.AVAILABLE


def test_wps_verified_evidence_does_not_cross_ms_only_tools(monkeypatch):
    """F7 回归:本进程内 PDF 转换回退 WPS 成功的 verified 证据,不得让仅 MS 的
    replace 展示"已验证可用";PDF 仍如实展示 WPS 已验证。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(False),
            "KWPS.Application": em._ProbeOutcome(True),
            "Excel.Application": em._ProbeOutcome(False),
            "Ket.Application": em._ProbeOutcome(False),
            "PowerPoint.Application": em._ProbeOutcome(False),
            "KWPP.Application": em._ProbeOutcome(False),
        },
    )
    EngineManager._mark_kind_verified("word", "wps")
    replace_status = next(
        status
        for status in tool_capability_statuses("replace")
        if status.requirement.startswith("Word")
    )
    assert replace_status.state is ProbeState.MISSING
    assert replace_status.verified is False
    assert "WPS" in replace_status.detail
    pdf_status = next(
        status
        for status in tool_capability_statuses("pdf")
        if status.requirement.startswith("Word")
    )
    assert pdf_status.state is ProbeState.AVAILABLE
    assert pdf_status.verified is True
    assert "WPS" in pdf_status.detail


def test_dual_suite_machine_keeps_ms_prescreen_for_ms_only_tools(monkeypatch):
    """F7 反向回归:MS+WPS 都注册且 PDF 回退 WPS 成功(verified=wps)时,仅 MS
    的 replace 仍展示 MS 预筛可用(未验证),不得图 WPS 叠加被误标 MISSING/
    继承 WPS verified;PDF 如实展示实际成功的 WPS 已验证。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(True),
            "KWPS.Application": em._ProbeOutcome(True),
            "Excel.Application": em._ProbeOutcome(True),
            "Ket.Application": em._ProbeOutcome(True),
            "PowerPoint.Application": em._ProbeOutcome(True),
            "KWPP.Application": em._ProbeOutcome(True),
        },
    )
    EngineManager._mark_kind_verified("word", "wps")
    replace_status = next(
        status
        for status in tool_capability_statuses("replace")
        if status.requirement.startswith("Word")
    )
    assert replace_status.state is ProbeState.AVAILABLE
    assert replace_status.detail == "MS Office"
    assert replace_status.verified is False  # 不继承 WPS verified
    pdf_status = next(
        status
        for status in tool_capability_statuses("pdf")
        if status.requirement.startswith("Word")
    )
    assert pdf_status.state is ProbeState.AVAILABLE
    assert pdf_status.detail == "WPS"
    assert pdf_status.verified is True  # 实际成功套件优先于预筛偏好


# ---------------------------------------------------------------------------
# P4:MS 探测错误不终止探测——支持集合内如实选择,不丢 WPS 成功/原 MS 错误
# ---------------------------------------------------------------------------


def _patch_ms_error_wps_registered(monkeypatch) -> list[str]:
    return _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(None, "denied"),
            "KWPS.Application": em._ProbeOutcome(True),
        },
    )


def test_ms_probe_error_still_probes_wps_for_supported_engines(monkeypatch):
    """P4 回归:MS 探测 OSError 时仍探 WPS——支持 WPS 的调用方在 WPS 注册
    命中时如实可用,详情保留 MS 探测错误;无约束查询同样可用,不把 WPS
    成功丢成错误状态。"""
    probed = _patch_ms_error_wps_registered(monkeypatch)
    pdf_view = EngineManager().kind_availability("word", engines=("office", "wps"))
    assert pdf_view.state is ProbeState.AVAILABLE
    assert pdf_view.engine == "wps"
    assert "denied" in pdf_view.detail  # 保留原 MS 探测错误
    unrestricted = EngineManager().kind_availability("word")
    assert unrestricted.state is ProbeState.AVAILABLE
    assert unrestricted.engine == "wps"
    assert "KWPS.Application" in probed  # WPS 实际被探测


def test_ms_probe_error_kept_for_ms_only_tools(monkeypatch):
    """P4 回归:仅 MS 工具在 MS 探测错误 + WPS 注册时保留原 PROBE_ERROR——
    不冒称缺失( MISSING),也不丢原错误。"""
    _patch_outcomes(
        monkeypatch,
        {
            "Word.Application": em._ProbeOutcome(None, "denied"),
            "KWPS.Application": em._ProbeOutcome(True),
            "Excel.Application": em._ProbeOutcome(False),
            "Ket.Application": em._ProbeOutcome(False),
        },
    )
    replace_status = next(
        status
        for status in tool_capability_statuses("replace")
        if status.requirement.startswith("Word")
    )
    assert replace_status.state is ProbeState.PROBE_ERROR
    assert "denied" in replace_status.detail


def test_office_kind_status_appends_fallback_probe_error(monkeypatch):
    """P4 展示:回退命中但另一套件探测失败时,能力文案保留探测错误。"""
    _patch_ms_error_wps_registered(monkeypatch)
    status = office_kind_status("word", (".doc", ".docx"), engines=("office", "wps"))
    assert status.state is ProbeState.AVAILABLE
    assert "WPS" in status.detail and "denied" in status.detail


# ---------------------------------------------------------------------------
# P5:非 PDF 适配器经能力层登记真实 COM 成功证据
# ---------------------------------------------------------------------------


def test_record_office_session_success_feeds_verified_evidence(monkeypatch):
    """P5 回归:考勤等适配器登记的 COM 成功 → 同一 verified 证据可纠正预筛
    (含缺失),页面/自测前置读到"已验证";非法 kind/engine fail closed。"""
    _patch_outcomes(
        monkeypatch,
        {"Excel.Application": em._ProbeOutcome(False), "Ket.Application": em._ProbeOutcome(False)},
    )
    record_office_session_success("excel", "office")
    attendance = tool_capability_statuses("attendance")[0]
    assert attendance.state is ProbeState.AVAILABLE
    assert attendance.verified is True
    assert attendance.detail == "MS Office"
    with pytest.raises(ValueError, match="未知的 Office 应用类别"):
        record_office_session_success("wordx")
    with pytest.raises(ValueError, match="未知的引擎套件"):
        record_office_session_success("word", "kingsoft")


# ---------------------------------------------------------------------------
# GUI 页面能力提示:复用现有 label,纯路径提示不受引擎缺失影响(离屏)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _kind_office(monkeypatch, available: set[str]) -> None:
    monkeypatch.setattr(
        EngineManager,
        "kind_availability",
        lambda self, kind, refresh=False, engines=None: KindAvailability(
            kind,
            ProbeState.AVAILABLE if kind in available else ProbeState.MISSING,
            "office",
        ),
    )


def test_pdf_label_appends_per_kind_status(qt_app, monkeypatch, tmp_path):
    pytest.importorskip("file_toolbox.gui.dialogs.pdf_tab")
    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog

    monkeypatch.chdir(tmp_path)
    # 套件级缓存(以 Word 判定)双无,而 Excel 独立命中:两者互不连带
    EngineManager._cached_engines = {"office": False, "wps": False}
    _kind_office(monkeypatch, {"excel"})
    try:
        dialog = PDFGeneratorDialog()
        text = dialog.ui.label_engine_info.text()
        assert text.startswith("未检测到Office软件")  # 套件级(仅 Word)如实展示
        assert "按文件类型:" in text
        assert "Word(doc/docx): 未检测到" in text
        assert "Excel(xls/xlsx): 检测到" in text
        assert "PowerPoint(ppt/pptx): 未检测到" in text
        assert "预检结论" in text  # 不冒称真实 COM 可用
        dialog.close()
    finally:
        EngineManager._cached_engines = None


def test_replace_hint_lists_pure_and_office_types(qt_app, monkeypatch, tmp_path):
    pytest.importorskip("file_toolbox.gui.dialogs.replace_tab")
    from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog

    monkeypatch.chdir(tmp_path)
    _kind_office(monkeypatch, set())
    dialog = ContentReplaceDialog()
    text = dialog.ui.label_file_filter.text()
    assert "txt/md 纯文件处理" in text
    assert "Word(doc/docx): 未检测到" in text
    assert "Excel(xls/xlsx): 未检测到" in text
    dialog.close()


def test_markdown_hint_appends_pandoc_status(qt_app, monkeypatch, tmp_path):
    pytest.importorskip("file_toolbox.gui.dialogs.markdown_tab")
    from file_toolbox.gui.dialogs.markdown_tab import MarkdownConvertTab

    monkeypatch.chdir(tmp_path)
    tab = MarkdownConvertTab()
    docx_hint = tab.ui.lbl_hint.text()
    assert "内置 Pandoc(docx)" in docx_hint
    tab.ui.cmb_target.setCurrentIndex(1)
    xlsx_hint = tab.ui.lbl_hint.text()
    assert "纯库转换,无需 Office/Pandoc" in xlsx_hint
    tab.close()


def test_attendance_label_shows_excel_status(qt_app, monkeypatch, tmp_path):
    pytest.importorskip("file_toolbox.gui.dialogs.attendance_tab")
    from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab

    monkeypatch.chdir(tmp_path)
    _kind_office(monkeypatch, {"excel"})
    tab = AttendanceTab()
    text = tab.ui.label_excel_status.text()
    assert text != "Excel 能力：待检测"
    assert "Excel(xlsx): 检测到" in text
    assert "预检结论" in text
    tab.close()
