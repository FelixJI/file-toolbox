"""计划排布 Tab GUI 测试:控件结构、选项映射、模板导出、输出目录解析、端到端生成。

不触发真实 COM,仅基于程序化生成的虚构 xlsx。UI 由
generated/ui_plan_schedule_dialog.py(Ui_PlanScheduleDialog)构建,本测试验证接入正确。
"""

import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 用 QtWidgets 子模块做 importorskip(而非顶层 PySide6):后者只校验包可 import,
# 不触发 libEGL/libGL 原生库加载;真实 import QtWidgets 才会,缺库时应跳过而非收集失败。
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from file_toolbox.core.plan_schedule import (  # noqa: E402
    ScheduleOptions,
    ScheduleResult,
)
from file_toolbox.gui.controllers.plan_schedule_controller import (
    PlanScheduleController,  # noqa: E402
)
from file_toolbox.gui.dialogs.plan_schedule_tab import PlanScheduleTab  # noqa: E402
from file_toolbox.gui.generated.ui_plan_schedule_dialog import HEADERS  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app):
    return PlanScheduleTab()


def _make_input(make_xlsx, tmp_path, rows):
    return make_xlsx("清单.xlsx", {"S": rows})


# ==================== 控件结构 ====================


def test_tab_has_expected_table_headers(tab):
    """结果表格应预置 5 列业务表头,列数与表头一致。"""
    assert tab.ui.table.columnCount() == len(HEADERS)
    headers = [
        tab.ui.table.horizontalHeaderItem(i).text() for i in range(tab.ui.table.columnCount())
    ]
    assert headers == HEADERS


def test_tab_starts_ready(tab):
    """新建 Tab 无输入、无结果行、状态就绪、年份默认当前。"""
    assert tab.ui.edit_input.text() == ""
    assert tab.ui.table.rowCount() == 0
    assert tab.ui.lbl_status.text() == "就绪"
    assert tab.ui.spin_year.value() == date.today().year


# ==================== controller(无 Qt) ====================


def test_controller_build_options():
    assert PlanScheduleController.build_options(None) == ScheduleOptions(default_year=None)
    assert PlanScheduleController.build_options(2027) == ScheduleOptions(default_year=2027)


def test_controller_format_progress():
    assert PlanScheduleController.format_progress(1, 2, "生成 2026年9月") == (
        "[1/2] 生成 2026年9月"
    )


def test_controller_result_rows_flags_invalid():
    from file_toolbox.core.plan_schedule import InvalidRow, PlanItem

    result = ScheduleResult(output=Path("o.xlsx"))
    result.items = [PlanItem("A", date(2026, 9, 17), date(2026, 9, 21), row=2)]
    result.invalid = [InvalidRow(3, "倒挂")]

    rows = PlanScheduleController.result_rows(result)

    assert rows[0] == (["A", "2026-09-17", "2026-09-21", "5天", "已排布"], False)
    assert rows[1] == (["第3行", "", "", "", "无效:倒挂"], True)


def test_controller_summarize():
    from file_toolbox.core.plan_schedule import InvalidRow, PlanItem

    result = ScheduleResult(output=Path("out.xlsx"))
    result.items = [PlanItem("A", date(2026, 9, 17), date(2026, 9, 21))]
    assert PlanScheduleController.summarize(result) == "已排布 1 个项点 -> out.xlsx"
    result.invalid = [InvalidRow(3, "倒挂")]
    assert PlanScheduleController.summarize(result) == "已排布 1 个项点,1 行无效 -> out.xlsx"
    assert PlanScheduleController.summarize(ScheduleResult(error_message="没有可排布的项点")) == (
        "失败:没有可排布的项点"
    )
    assert PlanScheduleController.summarize(ScheduleResult()) == "失败:未生成输出"


def test_history_summary_label_plan_schedule():
    """历史对话框对 plan_schedule 记录生成摘要行。"""
    from file_toolbox.gui.dialogs.history_dialog import _summary_label

    label = _summary_label(
        "plan_schedule",
        {"item_count": 17, "month_count": 4, "invalid_count": 2, "output": "C:/o/计划排布.xlsx"},
    )
    assert "17 项点" in label and "4 月" in label and "无效 2" in label
    assert label.endswith("→ 计划排布.xlsx")


# ==================== Tab 行为 ====================


def test_browse_input_sets_edit(tab, make_xlsx, monkeypatch):
    """清单选择对话框接通,选中路径回填输入框。"""
    src = _make_input(make_xlsx, Path("."), [["项点名称", "起始日期", "终止日期"]])
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.plan_schedule_tab.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(src), ""),
    )
    tab._browse_input()
    assert tab.ui.edit_input.text() == str(src)


def test_browse_outdir_sets_edit(tab, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.plan_schedule_tab.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(tmp_path),
    )
    tab._browse_outdir()
    assert tab.ui.edit_outdir.text() == str(tmp_path)


def test_export_template_writes_file(tab, tmp_path, monkeypatch):
    """导出模板:写盘成功并弹完成框。"""
    target = tmp_path / "模板.xlsx"
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.plan_schedule_tab.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), ""),
    )
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append("info"))

    tab._export_template()

    assert target.is_file()
    assert infos == ["info"]


def test_export_template_failure_shows_critical(tab, tmp_path, monkeypatch):
    """模板写盘失败 → 严重错误框,不抛异常。"""
    monkeypatch.setattr(
        "file_toolbox.gui.dialogs.plan_schedule_tab.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(tmp_path / "t.xlsx"), ""),
    )
    monkeypatch.setattr(tab._svc, "write_template", MagicMock(side_effect=OSError("disk full")))
    criticals: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: criticals.append("crit"))

    tab._export_template()

    assert criticals == ["crit"]


def test_generate_without_input_warns(tab, monkeypatch):
    """未选清单点生成 → 警告框,不启动 worker。"""
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_a, text=None, **_k: warned.append(text or _a[-1])
    )
    tab._generate()
    assert warned and "请先选择" in warned[0]
    assert tab._worker is None


def test_generate_unsupported_suffix_warns(tab, tmp_path, monkeypatch):
    """清单后缀不支持 → 警告框,不启动 worker。"""
    f = tmp_path / "清单.csv"
    f.write_text("x")
    tab.ui.edit_input.setText(str(f))
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_a, text=None, **_k: warned.append(text or _a[-1])
    )
    tab._generate()
    assert warned and "不支持的格式" in warned[0]
    assert tab._worker is None


def test_resolve_outdir_chain(tab, make_xlsx, monkeypatch, tmp_path):
    """输出目录解析优先级:输入框 > 上次设置 > 清单所在目录 > 当前目录。"""
    monkeypatch.chdir(tmp_path)
    src = _make_input(make_xlsx, tmp_path, [["项点名称", "起始日期", "终止日期"]])
    tab.ui.edit_input.setText(str(src))
    sub = tmp_path / "pick"
    sub.mkdir()

    # 1. 无输入框内容、无设置 → 清单所在目录
    assert tab._resolve_outdir() == src.parent

    # 2. 上次输出目录(settings)仍存在 → 优先于清单目录
    from file_toolbox.common import settings

    settings.set("plan_schedule/last_output_dir", str(sub))
    assert tab._resolve_outdir() == sub

    # 3. 输入框内容最优先
    tab.ui.edit_outdir.setText(str(tmp_path))
    assert tab._resolve_outdir() == tmp_path


def test_options_reads_controls(tab):
    tab.ui.spin_year.setValue(2027)
    assert tab._options() == ScheduleOptions(default_year=2027)


def test_populate_table_items_and_invalid(tab):
    """结果表格:项点行 + 无效行(浅黄底)。"""
    from file_toolbox.core.plan_schedule import InvalidRow, PlanItem

    result = ScheduleResult(output=Path("o.xlsx"))
    result.items = [PlanItem("A", date(2026, 9, 17), date(2026, 9, 21), row=2)]
    result.invalid = [InvalidRow(4, "起始日期无法识别:xx")]

    tab._populate_table(result)

    assert tab.ui.table.rowCount() == 2
    assert tab.ui.table.item(0, 0).text() == "A"
    assert tab.ui.table.item(0, 3).text() == "5天"
    assert tab.ui.table.item(0, 4).text() == "已排布"
    assert tab.ui.table.item(1, 0).text() == "第4行"
    assert "起始日期无法识别" in tab.ui.table.item(1, 4).text()
    assert tab.ui.table.item(1, 4).background().color().name().lower() == "#fff2cc"
    assert tab.ui.table.item(0, 4).background().color().name().lower() != "#fff2cc"


def test_generate_reentry_guard_while_running(tab, monkeypatch, make_xlsx, tmp_path):
    """worker 运行中重复点击不重复启动。"""
    src = _make_input(
        make_xlsx, tmp_path, [["项点名称", "起始日期", "终止日期"], ["A", "9-17", "9-21"]]
    )
    tab.ui.edit_input.setText(str(src))
    running = MagicMock()
    running.isRunning.return_value = True
    tab._worker = running

    tab._generate()

    assert tab._worker is running  # 未被替换


def test_on_generate_failed_shows_critical(tab, monkeypatch):
    """worker 异常信号 → 严重错误框 + 状态生成失败,按钮恢复。"""
    criticals: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: criticals.append("crit"))
    tab._worker = MagicMock()  # 非 None,模拟运行中

    tab._on_generate_failed("boom")

    assert criticals == ["crit"]
    assert tab.ui.lbl_status.text() == "生成失败"
    assert tab.ui.btn_generate.isEnabled() is True
    assert tab._worker is None


def test_close_event_stops_running_worker(tab):
    """关闭时若 worker 仍在跑:quit+wait,引用置空。"""
    worker = MagicMock()
    worker.isRunning.return_value = True
    tab._worker = worker

    tab.closeEvent(QCloseEvent())

    worker.quit.assert_called_once()
    worker.wait.assert_called_once_with(3000)
    assert tab._worker is None


def test_close_event_without_worker_is_noop(tab):
    """无 worker 时直接关闭,不抛错。"""
    tab.closeEvent(QCloseEvent())
    assert tab._worker is None


# ==================== 端到端 Tab 流程(真实 worker + 虚构 xlsx) ====================


def _wait_worker_done(tab, app, timeout_ms: int = 10000) -> None:
    """轮询事件循环直到 worker 结束(_on_generate_ok/_on_generate_failed 置空引用)。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while tab._worker is not None:
        app.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("worker 未在超时内结束")
        time.sleep(0.01)


def test_generate_flow_success(tab, app, monkeypatch, make_xlsx, tmp_path):
    """选清单 → 生成 → worker 完成:输出落盘、表格填充、状态摘要、记录上次目录。"""
    monkeypatch.chdir(tmp_path)  # 隔离 settings/history(成功路径会写 last_output_dir)
    src = _make_input(
        make_xlsx,
        tmp_path,
        [
            ["项点名称", "起始日期", "终止日期"],
            ["A", date(2026, 9, 17), date(2026, 9, 21)],
            ["B", date(2026, 9, 21), date(2026, 9, 27)],
        ],
    )
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: infos.append("info"))
    tab.ui.edit_input.setText(str(src))
    tab.ui.edit_outdir.setText(str(tmp_path / "out"))

    tab._generate()
    assert tab.ui.btn_generate.isEnabled() is False  # 生成期间禁用
    _wait_worker_done(tab, app)

    out = tmp_path / "out" / "计划排布.xlsx"
    assert out.is_file()
    assert tab.ui.btn_generate.isEnabled() is True
    assert tab.ui.table.rowCount() == 2
    assert "已排布 2 个项点" in tab.ui.lbl_status.text()
    assert infos == ["info"]
    from file_toolbox.common import settings

    assert settings.get("plan_schedule/last_output_dir") == str(tmp_path / "out")


def test_generate_flow_all_invalid_warns(tab, app, monkeypatch, make_xlsx, tmp_path):
    """全部行无效 → 警告框 + 状态栏失败,不写输出。"""
    monkeypatch.chdir(tmp_path)
    src = _make_input(
        make_xlsx,
        tmp_path,
        [["项点名称", "起始日期", "终止日期"], ["倒挂", date(2026, 9, 2), date(2026, 9, 1)]],
    )
    warns: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append("warn"))
    tab.ui.edit_input.setText(str(src))
    tab.ui.edit_outdir.setText(str(tmp_path))

    tab._generate()
    _wait_worker_done(tab, app)

    assert warns == ["warn"]
    assert tab.ui.lbl_status.text().startswith("失败:")
    assert not (tmp_path / "计划排布.xlsx").exists()
