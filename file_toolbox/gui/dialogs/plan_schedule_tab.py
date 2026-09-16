"""计划排布 Tab:选清单 -> 后台生成按月排布工作簿 -> 结果表格。

把项点清单(项点名称/起始日期/终止日期)生成为按月分块、标记周末、体现项点内
第几天与逐日并行数的排布表(纯 openpyxl,不依赖 Office)。
UI 布局由 generated/ui_plan_schedule_dialog.py 的 Ui_PlanScheduleDialog(setupUi)
构建,本类只做信号连接 + 业务编排(与其他 Tab 一致)。
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QBrush, QCloseEvent, QColor
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QWidget

from file_toolbox.common import settings
from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.core.plan_schedule import (
    DEFAULT_OUTPUT_NAME,
    SUPPORTED_SUFFIXES,
    TEMPLATE_NAME,
    PlanScheduleService,
)
from file_toolbox.gui.controllers.plan_schedule_controller import PlanScheduleController
from file_toolbox.gui.generated.ui_plan_schedule_dialog import Ui_PlanScheduleDialog
from file_toolbox.gui.workers.plan_schedule_worker import PlanScheduleWorker

_FAIL_COLOR = QColor(255, 242, 204)  # 浅黄(无效行)
# 上次输出目录的 settings key:输出框留空时默认复用,避免每次落到程序目录
_LAST_OUTDIR_KEY = "plan_schedule/last_output_dir"
_logger = logging.getLogger(__name__)


class PlanScheduleTab(QWidget):
    """计划排布 Tab。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PlanScheduleDialog()
        self.ui.setupUi(self)
        self.ui.spin_year.setValue(date.today().year)
        # history_store 先于 svc 创建并注入:CLI 与 GUI 共用同一记录路径(记录下沉 service)
        self._history = JsonHistoryStore()
        self._svc = PlanScheduleService(history_store=self._history)
        self._controller = PlanScheduleController()
        self._close_pending = False
        self._worker: PlanScheduleWorker | None = None
        self._connect()

    @property
    def close_pending(self) -> bool:
        return self._close_pending

    def _connect(self) -> None:
        self.ui.btn_browse_input.clicked.connect(self._browse_input)
        self.ui.btn_template.clicked.connect(self._export_template)
        self.ui.btn_browse.clicked.connect(self._browse_outdir)
        self.ui.btn_generate.clicked.connect(self._generate)

    # --- 输入/输出选择 ---

    def _browse_input(self) -> None:
        exts = " ".join(f"*{ext}" for ext in SUPPORTED_SUFFIXES)
        path, _ = QFileDialog.getOpenFileName(self, "选择项点清单", "", f"Excel 文件 ({exts})")
        if path:
            self.ui.edit_input.setText(path)

    def _browse_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.ui.edit_outdir.setText(d)

    def _export_template(self) -> None:
        """导出输入清单模板(表头 + 两行示例),避免用户猜输入格式。"""
        suggested = Path(self._resolve_outdir()) / TEMPLATE_NAME
        path, _ = QFileDialog.getSaveFileName(
            self, "导出清单模板", str(suggested), "Excel 文件 (*.xlsx)"
        )
        if not path:
            return
        try:
            output = self._svc.write_template(Path(path))
        except Exception as e:  # noqa: BLE001 - 写盘失败给用户中文反馈而非崩溃
            _logger.exception("导出模板失败")
            QMessageBox.critical(self, "导出失败", f"模板写出失败:{e}")
            return
        QMessageBox.information(self, "导出完成", f"模板已写出:\n{output}")

    def _resolve_outdir(self) -> Path:
        """输出目录解析:输出框内容 > 上次输出目录(仍存在) > 清单所在目录 > 当前目录。"""
        text = self.ui.edit_outdir.text().strip()
        if text:
            return Path(text)
        last = settings.get(_LAST_OUTDIR_KEY)
        if isinstance(last, str) and last.strip() and Path(last.strip()).is_dir():
            return Path(last.strip())
        input_text = self.ui.edit_input.text().strip()
        if input_text:
            input_dir = Path(input_text).parent
            if input_dir.is_dir():
                return input_dir
        return Path(".")

    def _options(self) -> Any:
        return self._controller.build_options(
            self.ui.spin_year.value(), self.ui.cmb_cell.currentIndex()
        )

    # --- 生成 ---

    def _generate(self) -> None:
        input_text = self.ui.edit_input.text().strip()
        input_path = Path(input_text) if input_text else None
        if input_path is None or not input_path.is_file():
            QMessageBox.warning(self, "提示", "请先选择有效的项点清单文件")
            return
        if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            QMessageBox.warning(
                self,
                "提示",
                f"不支持的格式 {input_path.suffix},仅支持 {'/'.join(SUPPORTED_SUFFIXES)}",
            )
            return
        # 避免重复启动(重复点击不泄漏多个 worker)
        if self._worker is not None:
            return
        output = self._resolve_outdir() / DEFAULT_OUTPUT_NAME
        worker = PlanScheduleWorker(self._svc, input_path, output, self._options(), parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_generate_ok)
        worker.failed.connect(self._on_generate_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker  # 持有引用防 GC
        self.ui.btn_generate.setEnabled(False)
        self.ui.lbl_status.setText("生成中…")
        worker.start()

    def _on_progress(self, current: int, total: int, msg: str) -> None:
        self.ui.lbl_status.setText(self._controller.format_progress(current, total, msg))

    def _on_generate_ok(self, result: Any) -> None:
        self._populate_table(result)
        summary = self._controller.summarize(result)
        self.ui.lbl_status.setText(summary)
        if result.success:
            settings.set(_LAST_OUTDIR_KEY, str(Path(result.output).parent))
            if not self._close_pending:
                QMessageBox.information(self, "生成完成", summary)
        elif not self._close_pending:
            QMessageBox.warning(self, "未生成输出", summary + "\n\n输入清单未被修改。")

    def _on_generate_failed(self, msg: str) -> None:
        self.ui.lbl_status.setText("生成失败")
        if not self._close_pending:
            QMessageBox.critical(self, "生成失败", msg)

    def _populate_table(self, result: Any) -> None:
        """结果表格:项点行 + 无效行(无效行浅黄)。"""
        rows = self._controller.result_rows(result)
        self.ui.table.setRowCount(len(rows))
        for r, (values, is_failed) in enumerate(rows):
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if is_failed:
                    item.setBackground(QBrush(_FAIL_COLOR))
                self.ui.table.setItem(r, c, item)

    def _on_worker_finished(self) -> None:
        """只在真实 finished 后释放线程,并恢复按钮或完成延迟关闭。"""
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        worker.deleteLater()
        self.ui.btn_generate.setEnabled(True)
        if self._close_pending:
            self._close_pending = False
            QTimer.singleShot(0, self.window().close)

    def closeEvent(self, event: QCloseEvent) -> None:
        """同步生成不可由 quit 中断;保留窗口直到实际写盘线程退出。"""
        if self._worker is not None:
            self._close_pending = True
            self.ui.lbl_status.setText("正在等待排布写入完成,随后自动关闭…")
            event.ignore()
            return
        super().closeEvent(event)
