"""updater_widget 的 do_download 方法补充测试(mock download_and_verify)。

do_download 在 worker 线程执行,这里直接同步调用验证信号发射逻辑。
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from file_toolbox.gui.updater_widget import UpdateWorker
from file_toolbox.updater.errors import UpdateError
from file_toolbox.updater.versions import RemoteRelease


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _release() -> RemoteRelease:
    return RemoteRelease(
        version="1.0",
        zip_url="http://x/z.zip",
        checksum_url="http://x/checksums.txt",
        source="github",
    )


# ---------------------------------------------------------------------------
# do_download:成功(行 100-106)
# ---------------------------------------------------------------------------


def test_do_download_success(app, monkeypatch):
    """download_and_verify 成功 → emit verified + progress(行 100-106)。"""
    import file_toolbox.updater.downloader as dl_mod

    progress_calls = []

    def fake_download(release, on_progress=None):
        if on_progress:
            on_progress(50, 100)
            on_progress(100, 100)
            progress_calls.extend([(50, 100), (100, 100)])
        return Path("update.zip")

    monkeypatch.setattr(dl_mod, "download_and_verify", fake_download)
    worker = UpdateWorker()
    verified = []
    worker.verified.connect(lambda p: verified.append(p))
    prog = []
    worker.progress.connect(lambda d, t: prog.append((d, t)))
    worker.do_download(_release())
    assert verified == [Path("update.zip")]
    assert (50, 100) in prog


# ---------------------------------------------------------------------------
# do_download:UpdateError(行 107-108)
# ---------------------------------------------------------------------------


def test_do_download_update_error(app, monkeypatch):
    """download_and_verify 抛 UpdateError → emit failed(行 107-108)。"""
    import file_toolbox.updater.downloader as dl_mod

    monkeypatch.setattr(
        dl_mod,
        "download_and_verify",
        lambda *a, **k: (_ for _ in ()).throw(UpdateError("校验失败")),
    )
    worker = UpdateWorker()
    failed = []
    worker.failed.connect(lambda m: failed.append(m))
    worker.do_download(_release())
    assert failed == ["校验失败"]


# ---------------------------------------------------------------------------
# do_download:通用异常(行 109-110)
# ---------------------------------------------------------------------------


def test_do_download_generic_exception(app, monkeypatch):
    """download_and_verify 抛通用异常 → emit failed '下载失败: ...'(行 109-110)。"""
    import file_toolbox.updater.downloader as dl_mod

    monkeypatch.setattr(
        dl_mod,
        "download_and_verify",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("网络断开")),
    )
    worker = UpdateWorker()
    failed = []
    worker.failed.connect(lambda m: failed.append(m))
    worker.do_download(_release())
    assert len(failed) == 1
    assert "下载失败" in failed[0]
    assert "网络断开" in failed[0]
