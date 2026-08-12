"""更新 transport 的 loopback/本地 packaging seam 测试。"""

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from file_toolbox.updater import UpdateApplyStatus
from file_toolbox.updater.coordinator import UpdateCancelled
from file_toolbox.updater.transport import (
    LegacySetupBridge,
    build_feed_candidates,
    forward_proxy_environment,
)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


class _NoContentLengthHandler(_QuietHandler):
    def send_header(self, keyword: str, value: str) -> None:
        if keyword.casefold() != "content-length":
            super().send_header(keyword, value)


@contextmanager
def _serve(directory: Path, handler_type: type[_QuietHandler] = _QuietHandler) -> Iterator[str]:
    handler = partial(handler_type, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_prefix_candidates_preserve_order_and_end_with_direct_feed() -> None:
    direct = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"

    assert build_feed_candidates(["https://one.example", "https://two.example/"]) == (
        f"https://one.example/{direct}",
        f"https://two.example/{direct}",
        direct,
    )


def test_forward_proxy_environment_sets_both_cases_and_restores(monkeypatch) -> None:
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://before.invalid")

    with forward_proxy_environment("http://127.0.0.1:8899"):
        import os

        assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:8899"
        assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:8899"
        assert os.environ["http_proxy"] == "http://127.0.0.1:8899"
        assert os.environ["https_proxy"] == "http://127.0.0.1:8899"
        assert os.environ["NO_PROXY"] == ""
        assert os.environ["no_proxy"] == ""

    import os

    assert os.environ["HTTP_PROXY"] == "http://before.invalid"
    if os.name == "nt":
        assert os.environ["http_proxy"] == "http://before.invalid"
    else:
        assert "http_proxy" not in os.environ


def test_legacy_bridge_downloads_and_verifies_setup_from_one_loopback_feed(
    tmp_path: Path,
) -> None:
    feed = tmp_path / "feed"
    latest = feed / "github" / "releases" / "latest" / "download"
    pinned = feed / "github" / "releases" / "download" / "v0.3.0"
    latest.mkdir(parents=True)
    pinned.mkdir(parents=True)
    (latest / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"0.3.0"}]}',
        encoding="utf-8",
    )
    setup = pinned / "FileToolbox-Setup.exe"
    setup.write_bytes(b"signed setup placeholder")
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (pinned / "checksums.txt").write_text(f"{digest}  FileToolbox-Setup.exe\n", encoding="utf-8")
    launched: list[Path] = []
    progress: list[int] = []

    with _serve(feed) as base_url:
        bridge = LegacySetupBridge(
            feed_candidates=(f"{base_url}github/releases/latest/download/",),
            cache_root=tmp_path / "cache",
            launcher=launched.append,
        )
        assert bridge.check() == "0.3.0"
        (latest / "releases.win.json").write_text(
            '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"9.9.9"}]}',
            encoding="utf-8",
        )
        result = bridge.download_and_start(progress.append)

    assert result.status is UpdateApplyStatus.INSTALLER_STARTED
    assert launched == [tmp_path / "cache" / "0.3.0" / "FileToolbox-Setup.exe"]
    assert launched[0].read_bytes() == b"signed setup placeholder"
    assert progress[-1] == 100


def test_legacy_bridge_rejects_error_page_or_corrupt_setup(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    feed.mkdir()
    (feed / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"0.3.0"}]}',
        encoding="utf-8",
    )
    (feed / "FileToolbox-Setup.exe").write_bytes(b"html error page")
    (feed / "checksums.txt").write_text(f"{'0' * 64}  FileToolbox-Setup.exe\n", encoding="utf-8")

    with _serve(feed) as base_url:
        bridge = LegacySetupBridge(
            feed_candidates=(base_url,),
            cache_root=tmp_path / "cache",
            launcher=lambda _path: None,
        )
        assert bridge.check() == "0.3.0"
        result = bridge.download_and_start()

    assert result.status is UpdateApplyStatus.FAILED
    assert "完整性" in result.message


def test_legacy_bridge_maps_progress_cancellation_and_removes_partial_setup(
    tmp_path: Path,
) -> None:
    feed = tmp_path / "feed"
    feed.mkdir()
    (feed / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"0.3.0"}]}',
        encoding="utf-8",
    )
    setup = feed / "FileToolbox-Setup.exe"
    setup.write_bytes(b"setup bytes")
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (feed / "checksums.txt").write_text(f"{digest}  FileToolbox-Setup.exe\n", encoding="utf-8")
    launched: list[Path] = []
    progress_calls: list[int] = []

    def cancel(value: int) -> None:
        progress_calls.append(value)
        raise UpdateCancelled

    with _serve(feed) as base_url:
        bridge = LegacySetupBridge(
            feed_candidates=(base_url,),
            cache_root=tmp_path / "cache",
            launcher=launched.append,
        )
        assert bridge.check() == "0.3.0"
        result = bridge.download_and_start(cancel)

    assert result.status is UpdateApplyStatus.CANCELLED
    assert progress_calls
    assert launched == []
    assert not (tmp_path / "cache" / "0.3.0" / "FileToolbox-Setup.exe").exists()


def test_legacy_bridge_can_cancel_chunk_without_content_length(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    feed.mkdir()
    (feed / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"0.3.0"}]}',
        encoding="utf-8",
    )
    setup = feed / "FileToolbox-Setup.exe"
    setup.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (feed / "checksums.txt").write_text(f"{digest}  FileToolbox-Setup.exe\n", encoding="utf-8")
    launched: list[Path] = []
    progress_calls: list[int] = []

    def cancel(value: int) -> None:
        progress_calls.append(value)
        raise UpdateCancelled

    with _serve(feed, _NoContentLengthHandler) as base_url:
        bridge = LegacySetupBridge(
            feed_candidates=(base_url,),
            cache_root=tmp_path / "cache",
            launcher=launched.append,
        )
        assert bridge.check() == "0.3.0"
        result = bridge.download_and_start(cancel)

    assert result.status is UpdateApplyStatus.CANCELLED
    assert progress_calls == [0]
    assert launched == []
    assert not (tmp_path / "cache" / "0.3.0" / "FileToolbox-Setup.exe").exists()


def test_legacy_bridge_rejects_wrong_package_id_and_unsafe_version(tmp_path: Path) -> None:
    wrong_package = tmp_path / "wrong-package"
    wrong_package.mkdir()
    (wrong_package / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"OtherApp","Type":"Full","Version":"0.3.0"}]}',
        encoding="utf-8",
    )
    unsafe_version = tmp_path / "unsafe-version"
    unsafe_version.mkdir()
    (unsafe_version / "releases.win.json").write_text(
        '{"Assets":[{"PackageId":"FileToolbox","Type":"Full","Version":"../0.3.0"}]}',
        encoding="utf-8",
    )

    with _serve(wrong_package) as wrong_url, _serve(unsafe_version) as unsafe_url:
        bridge = LegacySetupBridge(
            feed_candidates=(wrong_url, unsafe_url),
            cache_root=tmp_path / "cache",
            launcher=lambda _path: None,
        )
        try:
            bridge.check()
        except RuntimeError as error:
            assert str(error) == "无法读取 Velopack 更新 feed"
        else:
            raise AssertionError("损坏 feed 不应产生 bridge 目标版本")
