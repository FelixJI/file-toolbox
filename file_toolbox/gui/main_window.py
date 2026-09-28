"""File Toolbox 主窗口：QMainWindow + 9 个功能 Tab。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QByteArray, QMetaObject, QRect, Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.logging_config import configure_logging
from file_toolbox.common.metadata import runtime_version
from file_toolbox.common.paths import current_data_root_policy, use_data_root_policy
from file_toolbox.common.runtime import is_packaged_runtime
from file_toolbox.gui.freeze_watchdog import FreezeWatchdog
from file_toolbox.gui.updater_widget import UpdateBanner, UpdateWorker
from file_toolbox.updater import create_update_coordinator
from file_toolbox.updater.coordinator import UpdateCoordinator, UpdateRequest
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)

if TYPE_CHECKING:
    # Tab 类仅在类型标注中使用;运行时导入延迟到各 _make_*_tab 工厂,
    # 避免 dialogs 包(及其重依赖 pypdfium2/pypdf/chardet/cattrs)进入启动链。
    from file_toolbox.gui.dialogs.about_tab import AboutTab
    from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab
    from file_toolbox.gui.dialogs.excel_merge_tab import ExcelMergeTab
    from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab
    from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog
    from file_toolbox.gui.dialogs.pdf_sort_tab import PdfSortTab
    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog
    from file_toolbox.gui.dialogs.plan_schedule_tab import PlanScheduleTab
    from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog
    from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog
    from file_toolbox.gui.dialogs.update_tab import UpdateTab

_logger = logging.getLogger(__name__)

# 窗口几何持久化 key(settings.json):base64(saveGeometry)。
_GEOMETRY_KEY = "window/geometry"
# 独立更新页在标签栏中的固定索引(9 个业务页之后、关于页之前)。
_UPDATE_TAB_INDEX = 9


def _make_rename_tab() -> FileRenamerDialog:
    from file_toolbox.gui.dialogs.rename_tab import FileRenamerDialog

    return FileRenamerDialog()


def _make_mkdir_tab() -> BatchFolderCreatorDialog:
    from file_toolbox.gui.dialogs.mkdir_tab import BatchFolderCreatorDialog

    return BatchFolderCreatorDialog()


def _make_pdf_tab() -> PDFGeneratorDialog:
    from file_toolbox.gui.dialogs.pdf_tab import PDFGeneratorDialog

    return PDFGeneratorDialog()


def _make_replace_tab() -> ContentReplaceDialog:
    from file_toolbox.gui.dialogs.replace_tab import ContentReplaceDialog

    return ContentReplaceDialog()


def _make_attendance_tab() -> AttendanceTab:
    from file_toolbox.gui.dialogs.attendance_tab import AttendanceTab

    return AttendanceTab()


def _make_invoice_tab() -> InvoiceTab:
    from file_toolbox.gui.dialogs.invoice_tab import InvoiceTab

    return InvoiceTab()


def _make_excel_merge_tab() -> ExcelMergeTab:
    from file_toolbox.gui.dialogs.excel_merge_tab import ExcelMergeTab

    return ExcelMergeTab()


def _make_pdf_sort_tab() -> PdfSortTab:
    from file_toolbox.gui.dialogs.pdf_sort_tab import PdfSortTab

    return PdfSortTab()


def _make_plan_schedule_tab() -> PlanScheduleTab:
    from file_toolbox.gui.dialogs.plan_schedule_tab import PlanScheduleTab

    return PlanScheduleTab()


def _make_update_tab() -> UpdateTab:
    from file_toolbox.gui.dialogs.update_tab import UpdateTab

    return UpdateTab()


def _make_about_tab() -> AboutTab:
    from file_toolbox.gui.dialogs.about_tab import AboutTab

    return AboutTab()


def _construct_tab(factory: Callable[[], QWidget], name: str) -> QWidget:
    """构造一个功能 Tab 并记录耗时(偶发启动卡顿时定位到具体 Tab)。"""
    t0 = time.perf_counter()
    tab = factory()
    _logger.debug("Tab 构造完成 tab=%s 耗时=%.0fms", name, (time.perf_counter() - t0) * 1000)
    return tab


class MainWindow(QMainWindow):
    """工具箱主窗口，9 个功能 Tab。"""

    def __init__(self, coordinator: UpdateCoordinator | None = None) -> None:
        super().__init__()
        self.setWindowTitle("File Toolbox")
        self._restore_window_geometry()

        self._history = JsonHistoryStore()

        central = QWidget()
        layout = QVBoxLayout(central)
        # 主区域不留外边距,避免标签栏上方出现一片空白带
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部:历史按钮(直接对应当前标签页,无需二次选择;右对齐)
        top = QHBoxLayout()
        top.setContentsMargins(9, 5, 9, 2)
        top.addStretch(1)
        self.btn_history = QToolButton()
        self.btn_history.setText("历史")
        self.btn_history.clicked.connect(self._open_history_for_current_tab)
        top.addWidget(self.btn_history)
        layout.addLayout(top)

        # 9 个功能 Tab + 更新 + 关于:Tab 类与重依赖(pypdfium2/pypdf/chardet/cattrs)
        # 均懒导入,首次构造某 Tab 时才 import;首屏只构造重命名 Tab。
        # 打包形态下真实平台主窗口构造可达 ~1.7s,大头是首个控件初始化链
        # 之后的各 Tab 陆续构造;懒掉非首屏 Tab 让首帧只付首 Tab 的成本。
        tabs = QTabWidget()
        self._tabs = tabs
        self._tab_error_message: str | None = None
        self._status_before_tab_error = ""
        self._rename_tab: FileRenamerDialog | None = None
        self._mkdir_tab: BatchFolderCreatorDialog | None = None
        self._pdf_tab: PDFGeneratorDialog | None = None
        self._replace_tab: ContentReplaceDialog | None = None
        self._attendance_tab: AttendanceTab | None = None
        self._invoice_tab: InvoiceTab | None = None
        self._excel_merge_tab: ExcelMergeTab | None = None
        self._pdf_sort_tab: PdfSortTab | None = None
        self._plan_schedule_tab: PlanScheduleTab | None = None
        self._update_tab: UpdateTab | None = None
        self._about_tab: AboutTab | None = None
        # 懒构造登记:index -> (标签文本, Tab 工厂, 属性名);占位页被真实 Tab 原位替换。
        # 含首屏(重命名):由 __init__ 末尾的 _on_tab_changed 统一触发构造。
        self._lazy_specs: dict[int, tuple[str, Callable[[], QWidget], str]] = {
            index: (label, factory, attr)
            for index, (label, factory, attr) in enumerate(
                [
                    ("重命名", _make_rename_tab, "_rename_tab"),
                    ("建文件夹", _make_mkdir_tab, "_mkdir_tab"),
                    ("生成PDF", _make_pdf_tab, "_pdf_tab"),
                    ("内容替换", _make_replace_tab, "_replace_tab"),
                    ("考勤汇总", _make_attendance_tab, "_attendance_tab"),
                    ("发票识别", _make_invoice_tab, "_invoice_tab"),
                    ("Excel合并", _make_excel_merge_tab, "_excel_merge_tab"),
                    ("PDF排序", _make_pdf_sort_tab, "_pdf_sort_tab"),
                    ("计划排布", _make_plan_schedule_tab, "_plan_schedule_tab"),
                    ("更新", _make_update_tab, "_update_tab"),
                    ("关于", _make_about_tab, "_about_tab"),
                ]
            )
        }
        self._tab_attrs = tuple(spec[2] for spec in self._lazy_specs.values())
        self._closing_workers: set[QThread] = set()
        self._restart_pending = False
        self._close_requested = False
        for label, _factory, _attr in self._lazy_specs.values():
            tabs.addTab(QWidget(), label)
        # 各 Tab 对应的历史工具名;"更新"/"关于"页无历史 → None(按钮禁用)
        self._tab_tools: list[str | None] = [
            "rename",
            "mkdir",
            "pdf",
            "replace",
            "attendance",
            "invoice",
            "excel_merge",
            "pdf_sort",
            "plan_schedule",
            None,
            None,
        ]
        tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(tabs, stretch=1)

        central.setLayout(layout)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

        # --- 自更新:状态栏 banner + 后台 worker(仅便携 exe 形态启用检查) ---
        self._update_banner = UpdateBanner()
        self.statusBar().addPermanentWidget(self._update_banner)
        # 每轮检查经工厂重读代理设置:保存代理后下一轮检查即生效,无需重启窗口。
        # ContextVar 不随线程继承:工厂在 worker 线程执行,须用主线程捕获的
        # 数据根 policy 重新进入上下文,否则会落到 cwd 的 CLI 数据根。
        # 注入 coordinator(测试)时工厂复用注入实例,保持测试缝隙不变。
        if coordinator is None:
            data_root_policy = current_data_root_policy()

            def _fresh_coordinator() -> UpdateCoordinator:
                with use_data_root_policy(data_root_policy):
                    return create_update_coordinator()

            initial_coordinator = _fresh_coordinator()
            coordinator_factory = _fresh_coordinator
        else:
            initial_coordinator = coordinator
            coordinator_factory = lambda: coordinator  # noqa: E731 — 闭包绑定参数
        self._update_worker = UpdateWorker(
            initial_coordinator, coordinator_factory=coordinator_factory
        )
        self._update_worker.progress.connect(self._on_update_progress)
        self._update_worker.applying.connect(self._on_update_applying)
        self._update_worker.applied.connect(self._on_update_applied)
        self._update_banner.clicked.connect(self._open_update_page)
        self._pending_update: UpdateCheckResult | None = None
        self._last_check: UpdateCheckResult | None = None
        self._download_request: UpdateRequest | None = None
        self._last_progress: int = 0
        self._startup_outcome = ""
        self._business_tabs_locked = False

        self._update_worker.checked.connect(self._on_update_checked)

        if is_packaged_runtime():
            # 仅打包产物(Nuitka/Velopack)形态自动检查;开发态仍可从关于页手动检查。
            # 不能只看 sys.frozen:Nuitka standalone 不设置它,便携包曾因此
            # 被当成开发态,自动检查从未运行。
            self._update_worker.start()
            QTimer.singleShot(0, self._trigger_check)

        # 上次 apply 的跨启动对账(成功/未完成的准确结果,见 #128 AC5)。
        self._report_update_outcome()

        # 历史按钮初始状态跟随当前(首个)标签页
        self._on_tab_changed(self._tabs.currentIndex())

    def _ensure_tab(self, index: int) -> None:
        """懒构造:用真实 Tab 原位替换占位页(标签与位置不变)。

        blockSignals 防止 removeTab/insertTab 期间 currentChanged 跳到别的
        占位页触发连锁构造;结束后恢复原 currentIndex(即被构造的 Tab)。
        """

        spec = self._lazy_specs.get(index)
        if spec is None:
            return
        label, factory, attr = spec
        del self._lazy_specs[index]
        try:
            tab = _construct_tab(factory, label)
        except BaseException:
            # 构造期间移出登记避免重入;失败必须恢复,让下次切换可以重试。
            self._lazy_specs[index] = spec
            raise
        setattr(self, attr, tab)
        if attr not in ("_update_tab", "_about_tab") and self._business_tabs_locked:
            # 下载期间允许切页查看,但懒构造的业务页必须按锁状态禁用,
            # 不能在下载中开始新的业务写入(#129 AC4)。
            tab.setEnabled(False)
        current = self._tabs.currentIndex()
        self._tabs.blockSignals(True)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, tab, label)
        self._tabs.setCurrentIndex(current)
        self._tabs.blockSignals(False)
        if attr == "_update_tab":
            # 更新页是唯一的更新主动作入口:请求信号接主窗口既有更新链
            update_tab = cast("UpdateTab", tab)
            update_tab.check_requested.connect(self._on_check_requested)
            update_tab.download_requested.connect(self._start_download)
            update_tab.cancel_requested.connect(self._on_download_cancel)
            if self._business_tabs_locked:
                update_tab.setEnabled(True)
            # 页面可能晚于状态创建:回放启动对账、最近检查与进行中的下载
            update_tab.set_startup_outcome(self._startup_outcome)
            if self._last_check is not None:
                update_tab.display_check_result(self._last_check)
            request = self._download_request
            if request is not None:
                version = self._pending_update.version if self._pending_update else ""
                update_tab.begin_download(version)
                update_tab.set_download_progress(self._last_progress)
                if request.applying:
                    update_tab.enter_apply_phase()
        elif attr == "_about_tab":
            # 关于页只保留"打开更新页面"导航,不再承载检查/下载动作
            about_tab = cast("AboutTab", tab)
            about_tab.open_update_page_requested.connect(self._open_update_page)

    def _materialize_all_tabs(self) -> None:
        """立即构造全部懒 Tab(测试与预热场景使用)。"""

        for index in sorted(self._lazy_specs):
            self._ensure_tab(index)

    def _on_tab_changed(self, index: int) -> None:
        """标签页切换:先补建懒 Tab,再更新历史按钮可用状态(关于页无历史 → 禁用)。"""

        try:
            self._ensure_tab(index)
        except Exception as error:
            _logger.exception("Tab 构造失败 index=%d", index)
            if self.statusBar().currentMessage() != self._tab_error_message:
                self._status_before_tab_error = self.statusBar().currentMessage()
            self._tab_error_message = f"页面加载失败，切换后可重试: {error}"
            self.statusBar().showMessage(self._tab_error_message)
            self.btn_history.setEnabled(False)
            return
        if self.statusBar().currentMessage() == self._tab_error_message:
            self.statusBar().showMessage(self._status_before_tab_error)
        self._tab_error_message = None
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        self.btn_history.setEnabled(
            tool is not None and self._download_request is None and not self._close_requested
        )

    def _open_history_for_current_tab(self) -> None:
        """点击历史按钮:直接打开当前标签页对应的历史(无需二次选择)。"""
        index = self._tabs.currentIndex()
        tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
        if tool is None:
            return
        from file_toolbox.gui.dialogs.history_dialog import HistoryDialog

        dlg = HistoryDialog(self._history, tool, self)
        dlg.exec()

    # --- 自更新槽方法 ---

    def _trigger_check(self) -> None:
        """向 worker 线程投递检查请求(跨线程 QueuedConnection)。"""
        if not self._update_worker.isRunning():
            return
        QMetaObject.invokeMethod(
            self._update_worker, "do_check", Qt.ConnectionType.QueuedConnection
        )

    def _on_check_requested(self) -> None:
        """更新页请求检查更新:确保 worker 运行并投递 do_check。"""
        if not self._update_worker.isRunning():
            # 非便携形态(pip/dev):按需启动 worker(自动检查不会启)
            self._update_worker.start()
        self._trigger_check()

    def _on_download_requested(self) -> None:
        """确保 worker 运行后复用 _start_download(旧关于页入口移除后供测试直调)。"""
        if not self._update_worker.isRunning():
            self._update_worker.start()
        self._start_download()

    def _on_update_checked(self, result: UpdateCheckResult) -> None:
        """单一状态入口:任何检查结果(自动/手动)驱动横幅、候选与关于页同一状态。

        非 AVAILABLE 结果必须清掉旧候选并隐藏横幅:过期 banner 不能继续触发
        旧更新(coordinator 每轮检查已重置绑定候选)。关于页已构造时实时回放,
        未构造时由 _ensure_tab 用 _last_check 补放。
        """
        self._last_check = result
        if result.status is UpdateCheckStatus.AVAILABLE:
            self._pending_update = result
            self._update_banner.show_result(result)
        else:
            self._pending_update = None
            self._update_banner.hide()
        if self._update_tab is not None:
            self._update_tab.display_check_result(result)

    def _open_update_page(self) -> None:
        """横幅/关于页入口统一导航到独立更新页,绝不直接启动下载。"""
        self._tabs.setCurrentIndex(_UPDATE_TAB_INDEX)

    def _start_download(self) -> None:
        """更新页"下载并更新" → 确认后锁业务页并向 worker 投递下载请求。

        进度、校验提示与取消都承载在更新页内(#129),不再弹独立进度对话框。
        """
        if (
            self._pending_update is None
            or self._download_request is not None
            or self._close_requested
        ):
            return
        if self._running_business_workers():
            QMessageBox.warning(self, "后台任务尚未结束", "请等待当前文件操作完成后再更新。")
            return
        update = self._pending_update
        prompt = f"将下载并应用 v{update.version}，应用会在准备完成后退出并重启。是否继续？"
        if (
            QMessageBox.question(
                self,
                "确认更新",
                prompt,
                QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Apply
        ):
            return
        # 确认对话框有嵌套事件循环,返回后再次核对;不能在 SDK 接管后才等待业务。
        if self._close_requested:
            return
        if self._running_business_workers():
            QMessageBox.warning(self, "后台任务尚未结束", "请等待当前文件操作完成后再更新。")
            return
        update_tab = self._update_tab
        if update_tab is None:
            # 下载只能从更新页发起;防御懒构造态异常路径
            return
        self._set_business_tabs_locked(True)
        self.btn_history.setEnabled(False)
        self._update_banner.hide()
        # 先落对账记录再请求下载:apply 提交后跨启动才能比对目标版本;取消/
        # 未进入 apply 的失败在 _on_update_applied 清除,apply 阶段的不确定结果
        # 保留给下次启动对账。
        self._record_pending_apply(update.version)
        request = self._update_worker.start_download(expected_version=update.version)
        if request is None:
            self._clear_pending_apply_record()
            self._restore_retry_affordances()
            return
        self._download_request = request
        self._last_progress = 0
        update_tab.begin_download(update.version)

    def _on_download_cancel(self) -> None:
        """只有提交门接受取消才显示取消;等待该请求结束后开放重试。"""
        request = self._download_request
        if request is None:
            return
        if self._update_worker.cancel_download(request):
            self.statusBar().showMessage("正在取消更新，请等待当前请求结束…")
            if self._update_tab is not None:
                self._update_tab.set_cancelling()
        elif request.applying:
            self._on_update_applying(request)
        else:
            self.statusBar().showMessage("更新请求已结束，正在确认结果…")

    def _on_update_applying(self, request: UpdateRequest) -> None:
        if request is not self._download_request:
            return
        self.statusBar().showMessage("正在应用更新，已无法取消；完成后将重启。")
        if self._update_tab is not None:
            self._update_tab.enter_apply_phase()

    def _restore_retry_affordances(self) -> None:
        """下载取消/失败后恢复重试入口(状态栏横幅 + 更新页/业务页)。"""
        if self._pending_update is not None:
            self._update_banner.show()
        if not self._close_requested:
            self._set_business_tabs_locked(False)
            index = self._tabs.currentIndex()
            tool = self._tab_tools[index] if 0 <= index < len(self._tab_tools) else None
            self.btn_history.setEnabled(tool is not None)
        if self._update_tab is not None:
            self._update_tab.finish_download(restored=self._pending_update is not None)

    def _set_business_tabs_locked(self, locked: bool) -> None:
        """下载期间锁定业务页(不能开始新的业务写入),更新/关于页保持可用。

        不整体禁用 Tab 容器:页面可切换查看,更新页的进度与可取消阶段的取消
        按钮必须保持可用。此后懒构造的业务页也按当前锁状态初始化。
        """
        self._business_tabs_locked = locked
        for attr in self._tab_attrs:
            if attr in ("_update_tab", "_about_tab"):
                continue
            tab = getattr(self, attr)
            if tab is not None:
                tab.setEnabled(not locked)

    def _on_update_progress(self, request: UpdateRequest, value: int) -> None:
        if request is not self._download_request:
            return
        self._last_progress = value
        if self._update_tab is not None:
            self._update_tab.set_download_progress(value)

    def _on_update_applied(self, request: UpdateRequest, result: UpdateApplyResult) -> None:
        """只消费当前请求结果,旧结果不能关闭新请求或安排重复退出。"""
        if request is not self._download_request:
            return
        self._download_request = None
        if result.status is UpdateApplyStatus.CANCELLED:
            self._clear_pending_apply_record()
            self.statusBar().showMessage("更新已取消。")
            if self._update_tab is not None:
                self._update_tab.set_status_message("更新已取消,可重新下载。")
            self._restore_retry_affordances()
            return
        if result.status is UpdateApplyStatus.FAILED and request.applying:
            self._download_request = request
            self.statusBar().showMessage("更新应用结果不确定，请检查更新状态后重新启动应用。")
            if self._update_tab is not None:
                # 页面必须如实呈现"结果不确定":不复原重试入口(防重复提交),
                # 也不能继续宣称"正在应用,完成后将重启"。
                self._update_tab.set_uncertain(
                    "更新应用结果不确定，请检查更新状态后重新启动应用；不要重复提交更新。"
                )
            QMessageBox.warning(
                self,
                "更新应用结果不确定",
                f"{result.message}\n\n已进入应用阶段，无法确认更新器是否接管；"
                "请检查更新状态后重新启动应用，不要重复提交更新。",
            )
            return
        if result.status is UpdateApplyStatus.FAILED:
            self._clear_pending_apply_record()
            QMessageBox.warning(
                self,
                "更新失败",
                f"{result.message}\n\n原程序未受影响,可稍后重试。",
            )
            if self._update_tab is not None:
                self._update_tab.set_status_message(f"更新失败: {result.message}", "failed")
            self._restore_retry_affordances()
            return
        self._shutdown_for_restart()

    # --- 跨启动更新对账(#128 AC5) ---

    _PENDING_APPLY_KEY = "update/pending_apply"

    def _record_pending_apply(self, version: str) -> None:
        """用户确认更新后写入预期目标版本(仅用于下次启动对账,非第二真相源)。"""
        from datetime import UTC, datetime

        from file_toolbox.common import settings

        try:
            settings.set(
                self._PENDING_APPLY_KEY,
                {
                    "target_version": version,
                    "written_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            # 记录失败不阻断更新:下次启动只是无法对账,降级为不提示。
            _logger.exception("写入更新对账记录失败 target=%s", version)

    def _clear_pending_apply_record(self) -> None:
        """取消/未提交 apply 的失败:清除对账记录。"""
        from file_toolbox.common import settings

        try:
            settings.set(self._PENDING_APPLY_KEY, None)
        except Exception:
            _logger.exception("清除更新对账记录失败")

    def _report_update_outcome(self) -> None:
        """启动时对账上次 apply:以真实运行版本给出准确结果,而非依赖上次的显示状态。

        APPLY_STARTED/窗口重新出现都不代表更新成功;只有"当前运行版本 ==
        预期目标"才报成功,其余给出准确的未完成/不确定提示。记录一次性消费,
        不无限重试或重复 apply。
        """
        from file_toolbox.common import settings
        from file_toolbox.updater.runtime_support import probe_update_runtime

        record = settings.get(self._PENDING_APPLY_KEY)
        if not isinstance(record, dict):
            return
        target = str(record.get("target_version") or "")
        current = runtime_version()
        state = probe_update_runtime()
        self._clear_pending_apply_record()
        if target and current == target:
            message = f"已成功更新到 v{target}"
        elif state.available and state.pending_restart_version:
            message = f"更新已下载待应用: 当前 v{current}，待应用 v{state.pending_restart_version}"
        elif target:
            message = (
                f"上次更新未确认完成: 当前 v{current}，目标 v{target}；"
                "如仍为旧版请到“更新”页面重新检查更新"
            )
        else:
            message = "上次更新结果未知，请到“更新”页面检查更新确认当前版本"
        _logger.info("更新对账: %s (sdk_available=%s)", message, state.available)
        self._startup_outcome = message
        self.statusBar().showMessage(message, 15000)

    def _shutdown_for_restart(self) -> None:
        """更新已交给 Velopack;仍须经过与普通关闭相同的业务收尾。"""
        self._restart_pending = True
        self.close()

    # --- 窗口几何 ---

    def _restore_window_geometry(self) -> None:
        """恢复上次窗口几何;无记录/记录越界(如换了显示器)时回退屏幕自适应默认值。"""
        from file_toolbox.common import settings

        blob = settings.get(_GEOMETRY_KEY)
        restored = False
        if isinstance(blob, str) and blob:
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(blob.encode("ascii")))
            except ValueError:  # 损坏/非 base64 记录 → 当作无记录
                restored = False
        if restored and self._frame_on_some_screen():
            if not self.isMaximized():
                avail = self._available_geometry()
                self.resize(min(self.width(), avail.width()), min(self.height(), avail.height()))
            return
        self._apply_default_geometry()

    def _frame_on_some_screen(self) -> bool:
        """窗口是否与任一屏幕可视区有交集(防恢复到已拔掉的显示器上)。"""
        frame = self.frameGeometry()
        return any(frame.intersects(s.availableGeometry()) for s in QGuiApplication.screens())

    def _available_geometry(self) -> QRect:
        return (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()

    def _apply_default_geometry(self) -> None:
        """默认尺寸 950×640,且不超过当前屏幕可视区(高分屏缩放/小屏自动收窄)。"""
        avail = self._available_geometry()
        self.resize(min(950, avail.width() - 40), min(640, avail.height() - 60))

    def _persist_window_geometry(self) -> None:
        """保存窗口几何(含最大化状态)到 settings。"""
        from file_toolbox.common import settings

        settings.set(_GEOMETRY_KEY, bytes(self.saveGeometry().toBase64().data()).decode("ascii"))

    def _running_business_workers(self) -> list[QThread]:
        return [
            worker
            for attr in self._tab_attrs
            if (tab := getattr(self, attr)) is not None
            for worker in tab.findChildren(QThread)
            if worker.isRunning()
        ]

    def _on_closing_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, QThread):
            self._closing_workers.discard(worker)
        if not self._closing_workers:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:
        from PySide6.QtWidgets import QApplication

        # 登记表来自同一 Tab 注册源;getattr 不会构造尚未打开的页。
        tabs = [getattr(self, attr) for attr in self._tab_attrs]
        self._close_requested = True
        self._tabs.setEnabled(False)  # 关闭期间不再启动新的业务写入。
        self.btn_history.setEnabled(False)
        try:
            workers = self._running_business_workers()
            workers.append(self._update_worker)
            for worker in workers:
                if not worker.isRunning():
                    continue
                if worker not in self._closing_workers:
                    worker.finished.connect(self._on_closing_worker_finished)
                    # 订阅前后都可能恰好退出:复查避免错过 finished 后永久等待。
                    if not worker.isRunning():
                        continue
                    self._closing_workers.add(worker)
                cancel = getattr(worker, "cancel", None)
                if callable(cancel):
                    cancel()
                # 只请求更新线程的事件循环退出;业务线程由其取消契约结束。
                if worker is self._update_worker:
                    worker.quit()
        except Exception:
            _logger.exception("请求线程安全退出失败")
            event.ignore()
            return
        if self._closing_workers:
            self.statusBar().showMessage("正在等待后台任务安全结束,完成后自动关闭…")
            event.ignore()
            return

        try:
            self._persist_window_geometry()
        except Exception:
            _logger.exception("保存窗口几何失败,继续安全关闭")
        pending = False
        for tab in tabs:
            if tab is None:
                continue
            tab_event = QCloseEvent()
            try:
                tab.closeEvent(tab_event)
            except Exception:
                _logger.exception("关闭 Tab 失败 tab=%s", type(tab).__name__)
                tab_event.ignore()
            pending = (
                pending or not tab_event.isAccepted() or bool(getattr(tab, "close_pending", False))
            )
        if pending:
            event.ignore()
            return
        super().closeEvent(event)
        if self._restart_pending:
            self._restart_pending = False
            QApplication.quit()


def _activate_window(window: QWidget) -> None:
    """把既有主窗口取消最小化并提前(单实例守卫收到重复启动请求时调用)。"""

    window.setWindowState(
        (window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
    )
    window.show()
    window.raise_()
    window.activateWindow()


def run_gui() -> None:
    """启动 GUI(供 cli gui 子命令调用)。"""
    import sys

    from PySide6.QtWidgets import QApplication

    from file_toolbox.common.paths import current_data_root
    from file_toolbox.gui.single_instance import SingleInstanceGuard, server_name_for

    log_file = configure_logging(mode="gui")
    _logger.info("GUI 初始化")
    # 版本身份双记录:importlib(打包态为 Nuitka 内嵌元数据)与 Velopack 安装
    # 清单(更新器比对的真实身份)。二者不一致即可从日志定位"仍旧版"故障层。
    from file_toolbox.common.metadata import VERSION
    from file_toolbox.updater.runtime_support import packaged_version

    _logger.info(
        "版本身份 importlib=%s velopack=%s exe=%s", VERSION, packaged_version(), sys.executable
    )
    watchdog = FreezeWatchdog(log_file)
    t0 = time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv)
    _logger.info("QApplication 就绪 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    watchdog.start(app)
    guard = SingleInstanceGuard(server_name_for(current_data_root()))
    if not guard.acquire():
        # 重复启动:激活既有实例窗口后本进程退出,避免两个 GUI 抢写同一份
        # settings/历史,也避免用户看到"程序打开了两次"。
        _logger.info("检测到已运行的 GUI 实例,本次启动退出")
        return
    t0 = time.perf_counter()
    win = MainWindow()
    guard.activateRequested.connect(lambda: _activate_window(win))
    _logger.info("主窗口构造完成 耗时=%.0fms", (time.perf_counter() - t0) * 1000)
    win.show()
    _logger.info("进入事件循环")
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    run_gui()
