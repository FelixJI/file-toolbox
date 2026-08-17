"""BatchDialogMixin 的单元测试。

mock QFileDialog/QMessageBox,验证文件选择/文件夹/清空/worker 管理/信号清理等。
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication, QFileDialog, QListWidget, QMessageBox, QTableWidget

from file_toolbox.gui.batch_mixin import BatchDialogMixin, SignalManager


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _TestDialog(QObject, BatchDialogMixin):
    """可实例化的测试用混入子类(QObject 满足 QTimer/SignalManager 的 parent 要求)。"""

    SUPPORTED_FORMATS = {".txt", ".md"}
    PREVIEW_DEBOUNCE_MS = 10
    logger = logging.getLogger("test")

    def __init__(self):
        super().__init__()
        self._init_batch_dialog()


# ---------------------------------------------------------------------------
# SignalManager
# ---------------------------------------------------------------------------


def test_signal_manager_add_and_disconnect(app):
    sm = SignalManager()
    signal = MagicMock()
    slot = MagicMock()
    sm.add_connection(signal, slot, "desc")
    signal.connect.assert_called_once_with(slot)
    assert len(sm._connections) == 1
    sm.disconnect_all()
    signal.disconnect.assert_called_once_with(slot)
    assert sm._connections == []


def test_signal_manager_add_connection_swallows_exception(app):
    """signal.connect 抛异常 → 吞掉(行 32-33)。"""
    sm = SignalManager()
    signal = MagicMock()
    signal.connect.side_effect = RuntimeError("connect fail")
    sm.add_connection(signal, MagicMock(), "desc")  # 不应抛
    assert sm._connections == []


def test_signal_manager_disconnect_all_swallows_runtime_error(app):
    """disconnect 抛 RuntimeError → suppress(行 37-38)。"""
    sm = SignalManager()
    signal = MagicMock()
    signal.disconnect.side_effect = RuntimeError("not connected")
    sm._connections = [(signal, MagicMock(), "")]
    sm.disconnect_all()  # 不应抛
    assert sm._connections == []


# ---------------------------------------------------------------------------
# _get_file_filter / _is_temp_file / _is_file_supported
# ---------------------------------------------------------------------------


def test_get_file_filter_with_formats(app):
    dlg = _TestDialog()
    f = dlg._get_file_filter()
    assert "*.txt" in f and "*.md" in f and "所有文件" in f


def test_get_file_filter_empty_formats(app):
    class _Empty(QObject, BatchDialogMixin):
        SUPPORTED_FORMATS = set()

    dlg = _Empty.__new__(_Empty)
    QObject.__init__(dlg)
    assert dlg._get_file_filter() == "所有文件 (*.*)"


def test_is_temp_file_word_temp(app):
    dlg = _TestDialog()
    assert dlg._is_temp_file(Path("~$doc.docx")) is True
    assert dlg._is_temp_file(Path("~lock")) is True


def test_is_temp_file_tmp_suffix(app):
    dlg = _TestDialog()
    assert dlg._is_temp_file(Path("a.tmp")) is True


def test_is_temp_file_normal(app):
    dlg = _TestDialog()
    assert dlg._is_temp_file(Path("normal.txt")) is False


def test_is_file_supported_normal(app):
    dlg = _TestDialog()
    assert dlg._is_file_supported(Path("a.txt")) is True
    assert dlg._is_file_supported(Path("a.MD")) is True  # 大写


def test_is_file_supported_unsupported(app):
    dlg = _TestDialog()
    assert dlg._is_file_supported(Path("a.pdf")) is False


def test_is_file_supported_temp_rejected(app):
    dlg = _TestDialog()
    assert dlg._is_file_supported(Path("~$a.txt")) is False


def test_is_file_supported_no_formats_allows_all(app):
    class _Empty(QObject, BatchDialogMixin):
        SUPPORTED_FORMATS = set()

    dlg = _Empty.__new__(_Empty)
    QObject.__init__(dlg)
    assert dlg._is_file_supported(Path("a.xyz")) is True


# ---------------------------------------------------------------------------
# _select_files(mock QFileDialog)
# ---------------------------------------------------------------------------


def test_select_files_adds_supported(app, monkeypatch, tmp_path):
    dlg = _TestDialog()
    lw = QListWidget()
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.md"
    f1.write_text("x")
    f2.write_text("y")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1), str(f2)], ""))
    dlg._select_files(lw, auto_preview=False)
    assert len(dlg.selected_files) == 2
    assert lw.count() == 2


def test_select_files_filters_unsupported(app, monkeypatch, tmp_path):
    """不支持的格式被过滤。"""
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.pdf"  # 不支持
    f1.write_text("x")
    f2.write_text("y")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1), str(f2)], ""))
    dlg._select_files(None, auto_preview=False)
    assert len(dlg.selected_files) == 1
    assert dlg.selected_files[0].name == "a.txt"


def test_select_files_dedup(app, monkeypatch, tmp_path):
    """重复文件不重复加入。"""
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    dlg.selected_files.append(f1)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1)], ""))
    dlg._select_files(None, auto_preview=False)
    assert len(dlg.selected_files) == 1


def test_select_files_no_files_noop(app, monkeypatch):
    """用户取消(无文件)→ 不改 selected_files。"""
    dlg = _TestDialog()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([], ""))
    dlg._select_files(None, auto_preview=False)
    assert dlg.selected_files == []


def test_select_files_auto_preview_refreshes(app, monkeypatch):
    """auto_preview=True → 调 _refresh_preview(行 106-109)。"""
    dlg = _TestDialog()
    refreshed = {"n": 0}
    monkeypatch.setattr(
        dlg, "_refresh_preview", lambda: refreshed.__setitem__("n", refreshed["n"] + 1)
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([], ""))
    dlg._select_files(None, auto_preview=True)
    # 无文件 → added_count=0 → 不 refresh
    assert refreshed["n"] == 0


def test_select_files_with_files_auto_preview(app, monkeypatch, tmp_path):
    """有文件加入 + auto_preview=True → 触发 _refresh_preview(行 108-109)。"""
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    refreshed = {"n": 0}
    monkeypatch.setattr(
        dlg, "_refresh_preview", lambda: refreshed.__setitem__("n", refreshed["n"] + 1)
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f1)], ""))
    dlg._select_files(None, auto_preview=True)
    assert refreshed["n"] == 1


def test_select_folder_with_files_auto_preview(app, monkeypatch, tmp_path):
    """文件夹加入文件 + auto_preview=True → 触发 _refresh_preview(行 159-160)。"""
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    refreshed = {"n": 0}
    monkeypatch.setattr(
        dlg, "_refresh_preview", lambda: refreshed.__setitem__("n", refreshed["n"] + 1)
    )
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dlg._select_folder(None, ask_recursive=True, auto_preview=True)
    assert refreshed["n"] == 1


# ---------------------------------------------------------------------------
# _select_folder(mock QFileDialog/QMessageBox)
# ---------------------------------------------------------------------------


def test_select_folder_non_recursive(app, monkeypatch, tmp_path):
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "ignore.pdf"
    f1.write_text("x")
    f2.write_text("y")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    lw = QListWidget()
    dlg._select_folder(lw, ask_recursive=True, auto_preview=False)
    assert any(p.name == "a.txt" for p in dlg.selected_files)
    assert not any(p.name == "ignore.pdf" for p in dlg.selected_files)


def test_select_folder_recursive(app, monkeypatch, tmp_path):
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text("y")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg._select_folder(None, ask_recursive=True, auto_preview=False)
    names = [p.name for p in dlg.selected_files]
    assert "a.txt" in names and "b.md" in names


def test_select_folder_cancelled(app, monkeypatch):
    """用户取消选目录 → 直接返回。"""
    dlg = _TestDialog()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    dlg._select_folder(None, auto_preview=False)
    assert dlg.selected_files == []


def test_select_folder_no_ask_recursive(app, monkeypatch, tmp_path):
    """ask_recursive=False → 不弹确认,非递归加入。"""
    dlg = _TestDialog()
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    question_calls = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: question_calls.append(1) or QMessageBox.StandardButton.No,
    )
    dlg._select_folder(None, ask_recursive=False, auto_preview=False)
    assert question_calls == []  # 未弹确认
    assert any(p.name == "a.txt" for p in dlg.selected_files)


def test_select_folder_recursive_no_formats(app, monkeypatch, tmp_path):
    """递归 + 无格式限制 → 加入所有文件(行 142-145)。"""

    class _Empty(QObject, BatchDialogMixin):
        SUPPORTED_FORMATS = set()
        logger = logging.getLogger("test")
        PREVIEW_DEBOUNCE_MS = 10

        def __init__(self):
            super().__init__()
            self._init_batch_dialog()

    dlg = _Empty()
    f1 = tmp_path / "a.xyz"
    f1.write_text("x")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg._select_folder(None, ask_recursive=True, auto_preview=False)
    assert any(p.name == "a.xyz" for p in dlg.selected_files)


def test_select_folder_recursive_dir_named_as_format_not_collected(app, monkeypatch, tmp_path):
    """递归 + SUPPORTED_FORMATS:名为支持后缀(如 notes.txt)的目录不被误收入 selected_files。

    回归测试:旧递归分支对每个 ext 跑 rglob(f"*{{ext}}") 且漏掉 is_file() 检查。
    rglob 会同时匹配目录——因此名为 notes.txt 的目录会被旧代码的 rglob("*.txt")
    命中并误收为文件。统一谓词修复后,目录被 is_file() 滤除。

    注:目录名必须用 *支持* 的后缀(.txt),否则旧 glob 根本不会命中它,测试即失去
    回归意义(同名 .pdf 在 SUPPORTED_FORMATS={.txt,.md} 下从未被匹配)。
    """
    dlg = _TestDialog()
    (tmp_path / "notes.txt").mkdir()  # 目录,名为 notes.txt(用支持后缀)
    (tmp_path / "real.txt").write_text("y")  # 正常文件
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dlg._select_folder(None, ask_recursive=True, auto_preview=False)
    names = [p.name for p in dlg.selected_files]
    assert "real.txt" in names
    assert "notes.txt" not in names  # 目录不被误收


# ---------------------------------------------------------------------------
# _clear_files
# ---------------------------------------------------------------------------


def test_clear_files(app):
    dlg = _TestDialog()
    dlg.selected_files = [Path("a.txt")]
    lw = QListWidget()
    lw.addItem("a.txt")
    tw = QTableWidget()
    tw.setRowCount(2)
    dlg._clear_files(lw, tw)
    assert dlg.selected_files == []
    assert lw.count() == 0
    assert tw.rowCount() == 0


def test_clear_files_no_widgets(app):
    dlg = _TestDialog()
    dlg.selected_files = [Path("a.txt")]
    dlg._clear_files()
    assert dlg.selected_files == []


# ---------------------------------------------------------------------------
# _refresh_preview / _do_refresh_preview / _stop_worker / _set_ui_enabled / 辅助
# ---------------------------------------------------------------------------


def test_refresh_preview_starts_timer(app):
    dlg = _TestDialog()
    dlg._refresh_preview()  # 不应抛


def test_do_refresh_preview_default_noop(app):
    dlg = _TestDialog()
    dlg._do_refresh_preview()  # 默认空实现


def test_stop_worker_none(app):
    """worker=None → 直接置 None(不崩)。"""
    dlg = _TestDialog()
    dlg.worker = None
    dlg._stop_worker()
    assert dlg.worker is None


def test_stop_worker_running_with_cancel(app):
    """worker 运行中且有 cancel → cancel + quit + wait(行 184-187)。"""
    dlg = _TestDialog()
    worker = MagicMock()
    worker.isRunning.return_value = True
    worker.wait.return_value = True  # 正常停止
    worker.cancel = MagicMock()  # 显式提供 cancel 属性
    dlg.worker = worker
    dlg._stop_worker()
    worker.cancel.assert_called_once()
    worker.quit.assert_called_once()
    assert dlg.worker is None


def test_stop_worker_running_without_cancel(app):
    """worker 运行中无 cancel 属性 → 仅 quit + wait。"""
    dlg = _TestDialog()
    worker = MagicMock(spec=QThread)
    worker.isRunning.return_value = True
    # 不设置 cancel 属性(MagicMock spec=QThread 不会有)
    worker.wait.return_value = True
    dlg.worker = worker
    dlg._stop_worker()
    worker.quit.assert_called_once()


def test_stop_worker_not_running(app):
    """worker 存在但未运行 → 直接置 None。"""
    dlg = _TestDialog()
    worker = MagicMock(spec=QThread)
    worker.isRunning.return_value = False
    dlg.worker = worker
    dlg._stop_worker()
    assert dlg.worker is None


def test_stop_worker_terminate_on_timeout(app):
    """wait 超时返回 False → terminate + 再 wait(行 188-193)。"""
    dlg = _TestDialog()
    worker = MagicMock(spec=QThread)
    worker.isRunning.return_value = True
    worker.wait.return_value = False  # 超时
    dlg.worker = worker
    dlg._stop_worker(timeout_ms=10)
    worker.terminate.assert_called_once()


def test_set_ui_enabled_default_noop(app):
    dlg = _TestDialog()
    dlg._set_ui_enabled(False)  # 默认空实现


def test_format_size(app):
    dlg = _TestDialog()
    assert dlg._format_size(1024) == "1.00 KB"


def test_get_file_info_returns_dict(app, tmp_path):
    dlg = _TestDialog()
    f = tmp_path / "a.txt"
    f.write_text("x")
    info = dlg._get_file_info(f)
    assert info["exists"] is True


def test_update_status_default_noop(app):
    dlg = _TestDialog()
    dlg._update_status()  # 默认空实现


def test_cleanup_batch_dialog(app):
    """_cleanup_batch_dialog 停 timer/worker/断信号(行 217-222)。"""
    dlg = _TestDialog()
    dlg._cleanup_batch_dialog()  # 不应抛


def test_init_batch_dialog_provides_fallback_logger(app):
    """回归:子类未提供 logger(旧版 FileRenamerDialog/ContentReplaceDialog)时,
    _init_batch_dialog 按子类模块名兜底,_cleanup_batch_dialog 不再抛 AttributeError。"""

    class _NoLogger(QObject, BatchDialogMixin):
        SUPPORTED_FORMATS = set()

        def __init__(self):
            super().__init__()
            self._init_batch_dialog()

    dlg = _NoLogger()
    assert dlg.logger.name == _NoLogger.__module__
    dlg._cleanup_batch_dialog()  # 旧实现在此抛 AttributeError: no attribute 'logger'
