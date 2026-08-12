"""更新源候选、forward proxy 环境与 legacy Setup bridge。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from file_toolbox.updater.coordinator import UpdateCancelled
from file_toolbox.updater.models import UpdateApplyResult, UpdateApplyStatus

_logger = logging.getLogger(__name__)
DEFAULT_FEED = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"
_SETUP_NAME = "FileToolbox-Setup.exe"
_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
_NO_PROXY_VARIABLES = ("NO_PROXY", "no_proxy")
_ENV_LOCK = RLock()
_CHUNK = 1024 * 1024
_PACKAGE_ID = "FileToolbox"
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def build_feed_candidates(
    prefixes: Iterable[str], *, direct_feed: str = DEFAULT_FEED
) -> tuple[str, ...]:
    """把 URL-prefix 候选映射为完整 feed base，并以 direct 收尾。"""

    result: list[str] = []
    for raw in prefixes:
        prefix = raw.strip().rstrip("/")
        if prefix:
            candidate = f"{prefix}/{direct_feed}"
            if candidate not in result:
                result.append(candidate)
    if direct_feed not in result:
        result.append(direct_feed)
    return tuple(result)


def _pin_candidate(candidate: str, version: str) -> str:
    marker = "/releases/latest/download/"
    if marker not in candidate:
        return candidate
    return candidate.replace(marker, f"/releases/download/v{version}/", 1)


def _normalize_semver(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("Velopack feed 的 Version 不是字符串")
    match = _SEMVER_PATTERN.fullmatch(raw.strip())
    if match is None:
        raise ValueError("Velopack feed 的 Version 不是合法 SemVer")
    major, minor, patch, prerelease, build = match.groups()
    normalized = f"{int(major)}.{int(minor)}.{int(patch)}"
    if prerelease:
        normalized += f"-{prerelease}"
    if build:
        normalized += f"+{build}"
    return normalized


@contextmanager
def forward_proxy_environment(proxy_url: str) -> Iterator[None]:
    """在 SDK 调用期间注入受控 forward proxy，并完整恢复进程环境。"""

    if not proxy_url.strip():
        yield
        return
    with _ENV_LOCK:
        names = (*_PROXY_VARIABLES, *_NO_PROXY_VARIABLES)
        previous: dict[str, tuple[str, str | None] | None]
        if os.name == "nt":
            previous = {
                name.casefold(): next(
                    (
                        (key, value)
                        for key, value in os.environ.items()
                        if key.casefold() == name.casefold()
                    ),
                    None,
                )
                for name in names
            }
        else:
            previous = {name: (name, os.environ.get(name)) for name in names}
        try:
            for name in _PROXY_VARIABLES:
                os.environ[name] = proxy_url.strip()
            for name in _NO_PROXY_VARIABLES:
                os.environ[name] = ""
            yield
        finally:
            for name in names:
                os.environ.pop(name, None)
            for saved in previous.values():
                if saved is not None and saved[1] is not None:
                    os.environ[saved[0]] = saved[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_setup_sha(content: str) -> str | None:
    for line in content.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == _SETUP_NAME and len(parts[0]) == 64:
            try:
                int(parts[0], 16)
            except ValueError:
                continue
            return parts[0].casefold()
    return None


def _launch_setup(path: Path) -> object:
    return subprocess.Popen([str(path)], close_fds=True)  # noqa: S603


class LegacySetupBridge:
    """not-installed 布局下载同版本 Setup；不解析或替换 nupkg。"""

    def __init__(
        self,
        *,
        feed_candidates: Iterable[str],
        cache_root: Path,
        launcher: Callable[[Path], object] = _launch_setup,
        forward_proxy: str = "",
    ) -> None:
        self._feed_candidates = tuple(feed_candidates)
        self._cache_root = cache_root
        self._launcher = launcher
        self._forward_proxy = forward_proxy
        self._version = ""
        self._selected_feed = ""

    def check(self) -> str:
        """读取 Velopack feed 的目标 full 版本，并固定同一 candidate 的版本化 base。"""

        for base in self._feed_candidates:
            try:
                with (
                    forward_proxy_environment(self._forward_proxy),
                    urllib.request.urlopen(f"{base}releases.win.json", timeout=30) as response,
                ):
                    feed = json.loads(response.read().decode("utf-8"))
                full_assets = [
                    asset
                    for asset in feed.get("Assets", [])
                    if (
                        isinstance(asset, dict)
                        and asset.get("Type") == "Full"
                        and asset.get("PackageId") == _PACKAGE_ID
                    )
                ]
                if len(full_assets) != 1:
                    raise ValueError("Velopack feed 未包含唯一 full 目标版本")
                self._version = _normalize_semver(full_assets[0].get("Version"))
                self._selected_feed = _pin_candidate(base, self._version)
                return self._version
            except Exception as error:
                _logger.info("Setup bridge feed 检查失败 base=%s: %s", base, error)
        raise RuntimeError("无法读取 Velopack 更新 feed")

    def download_and_start(
        self, progress: Callable[[int], None] | None = None
    ) -> UpdateApplyResult:
        """同一 candidate 下载 checksums + Setup，校验成功后启动。"""

        if not self._selected_feed or not self._version:
            return UpdateApplyResult(UpdateApplyStatus.FAILED, "请先检查更新")
        target_dir = self._cache_root / self._version
        target_dir.mkdir(parents=True, exist_ok=True)
        setup_path = target_dir / _SETUP_NAME
        last_error = "无法下载安装器"
        for base in (self._selected_feed,):
            try:
                with forward_proxy_environment(self._forward_proxy):
                    with urllib.request.urlopen(f"{base}checksums.txt", timeout=30) as response:
                        checksum_text = response.read().decode("utf-8")
                    expected = _expected_setup_sha(checksum_text)
                    if expected is None:
                        raise ValueError("checksums.txt 未包含安装器")
                    with urllib.request.urlopen(f"{base}{_SETUP_NAME}", timeout=60) as response:
                        total_header = response.headers.get("Content-Length")
                        total = int(total_header) if total_header else 0
                        downloaded = 0
                        with setup_path.open("wb") as handle:
                            while chunk := response.read(_CHUNK):
                                handle.write(chunk)
                                downloaded += len(chunk)
                                if progress is not None:
                                    value = min(99, downloaded * 100 // total) if total > 0 else 0
                                    progress(value)
                if _sha256(setup_path) != expected:
                    raise ValueError("安装器完整性校验失败")
                if progress is not None:
                    progress(100)
                self._launcher(setup_path)
                return UpdateApplyResult(UpdateApplyStatus.INSTALLER_STARTED)
            except UpdateCancelled:
                setup_path.unlink(missing_ok=True)
                return UpdateApplyResult(UpdateApplyStatus.CANCELLED)
            except Exception as error:  # true external boundary，尝试下一个完整 candidate
                last_error = str(error)
                _logger.info("Setup bridge candidate 失败 base=%s: %s", base, error)
                setup_path.unlink(missing_ok=True)
        return UpdateApplyResult(UpdateApplyStatus.FAILED, last_error)
