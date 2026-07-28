"""engine_manager 未覆盖分支补充测试。

覆盖行:
- 175-178: detect_engines_async 启动 daemon 线程(走 _run_async_detect)
- 302-303: close 时 app.Quit 抛异常 → except 记日志
"""

import time
from unittest.mock import MagicMock

from file_toolbox.core.batch_pdf.engine_manager import EngineManager

# ---------------------------------------------------------------------------
# detect_engines_async:启动线程(行 175-178)
# ---------------------------------------------------------------------------


def test_detect_engines_async_starts_thread_and_invokes_callback(monkeypatch):
    """detect_engines_async 启动 daemon 线程,最终调 callback(行 175-178)。

    替换 _run_async_detect 让其直接同步调 callback,验证线程被启动且 callback 触发。
    """
    em = EngineManager()
    captured = {}

    def fake_run(self, callback=None):
        # 模拟异步检测完成
        if callback:
            callback("Word.Application")

    monkeypatch.setattr(EngineManager, "_run_async_detect", fake_run)
    em.detect_engines_async(callback=lambda info: captured.setdefault("info", info))

    # 给线程一点时间执行
    time.sleep(0.2)
    assert captured.get("info") == "Word.Application"


# ---------------------------------------------------------------------------
# close:app.Quit 抛异常(行 302-303)
# ---------------------------------------------------------------------------


def test_close_quit_exception_logged(monkeypatch):
    """close 时 app.Quit 抛异常 → except 记日志,不中断(行 300-305)。"""
    em = EngineManager()
    bad_app = MagicMock()
    bad_app.Quit.side_effect = RuntimeError("quit boom")
    em._word_app = bad_app
    em._current_word_engine = "Word.Application"

    # 不应抛异常
    em.close(_from_del=True)  # from_del 跳过 gc

    # app 被置 None(即使 Quit 失败)
    assert em._word_app is None
    assert em._current_word_engine is None


def test_close_all_apps_quit_exception_continues(monkeypatch):
    """多个 app,某个 Quit 抛异常 → 继续关闭其余(行 300-305)。"""
    em = EngineManager()
    bad_word = MagicMock()
    bad_word.Quit.side_effect = RuntimeError("word quit boom")
    good_excel = MagicMock()
    em._word_app = bad_word
    em._excel_app = good_excel
    em._current_word_engine = "Word.Application"
    em._current_excel_engine = "Excel.Application"

    em.close(_from_del=True)

    # 两个 Quit 都被调用(异常不中断循环)
    bad_word.Quit.assert_called_once()
    good_excel.Quit.assert_called_once()
    assert em._word_app is None
    assert em._excel_app is None
