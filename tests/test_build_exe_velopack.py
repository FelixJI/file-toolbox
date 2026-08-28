"""build_exe vpk 命令与差量前驱包准备契约:锁定 --delta 与上一版下载策略。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_exe  # noqa: E402


def test_velopack_command_enables_delta() -> None:
    """vpk 命令固定 --delta 1,禁止回退到 None(关闭差量)。"""
    cmd = build_exe._velopack_command(
        "dotnet", Path("build/nuitka/FileToolbox"), "0.3.0", Path("build/velopack")
    )
    assert cmd[:4] == ["dotnet", "dnx", f"vpk@{build_exe._VPK_VERSION}", "--"]
    assert "--delta" in cmd
    assert cmd[cmd.index("--delta") + 1] == "1"
    assert "None" not in cmd


def test_velopack_command_locks_pack_identity() -> None:
    cmd = build_exe._velopack_command("dotnet", Path("pack"), "0.3.0", Path("out"))
    for flag, value in (
        ("--packId", build_exe._PRODUCT),
        ("--packVersion", "0.3.0"),
        ("--channel", "win"),
        ("--noInst", None),
    ):
        assert flag in cmd
        if value is not None:
            assert cmd[cmd.index(flag) + 1] == value


class _FakeRun:
    """按命令关键子串返回伪造 CompletedProcess 的 subprocess.run 替身。"""

    def __init__(self, routes: list[tuple[str, int, str]]) -> None:
        self._routes = routes
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> object:
        joined = " ".join(cmd)
        self.calls.append(cmd)
        for needle, code, stderr in self._routes:
            if needle in joined:
                return build_exe.subprocess.CompletedProcess(cmd, code, stderr=stderr)
        raise AssertionError(f"未预期的调用: {joined}")


def test_previous_full_nupkg_skips_without_any_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """仓库尚无正式 Release(404)时不下载、不启用 delta。"""
    fake = _FakeRun([("releases/latest", 1, "Not Found")])
    monkeypatch.setattr(build_exe.subprocess, "run", fake)

    assert build_exe._previous_full_nupkg(tmp_path, "0.3.0") is None


def test_previous_full_nupkg_skips_when_release_not_older(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最新 Release 不低于当前版本(本地重建已发布版本)时跳过,不与自身做差量。"""

    def _unexpected_download(cmd: list[str], **_: object) -> None:
        assert "release download" not in " ".join(cmd), "不应触发下载"

    monkeypatch.setattr(build_exe, "_latest_release_tag", lambda: "v0.3.0")
    monkeypatch.setattr(build_exe.subprocess, "run", _unexpected_download)

    assert build_exe._previous_full_nupkg(tmp_path, "0.3.0") is None


def test_previous_full_nupkg_downloads_older_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_exe, "_latest_release_tag", lambda: "v0.2.10")
    downloaded = tmp_path / "FileToolbox-0.2.10-full.nupkg"
    downloaded.write_bytes(b"nupkg")
    fake = _FakeRun([("release download", 0, "")])
    monkeypatch.setattr(build_exe.subprocess, "run", fake)

    result = build_exe._previous_full_nupkg(tmp_path, "0.3.0")

    assert result == downloaded


def test_previous_full_nupkg_fails_closed_on_download_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上一版 Release 存在但下载失败 → fail closed,不静默降级为仅 full。"""
    monkeypatch.setattr(build_exe, "_latest_release_tag", lambda: "v0.2.10")
    monkeypatch.setattr(
        build_exe.subprocess,
        "run",
        _FakeRun([("release download", 1, "network error")]),
    )

    with pytest.raises(RuntimeError, match="0.2.10"):
        build_exe._previous_full_nupkg(tmp_path, "0.3.0")


def test_previous_full_nupkg_rejects_unexpected_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_exe, "_latest_release_tag", lambda: "release-2024")
    with pytest.raises(RuntimeError, match="tag"):
        build_exe._previous_full_nupkg(tmp_path, "0.3.0")
