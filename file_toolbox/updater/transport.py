"""更新源候选与 forward proxy 环境。"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from threading import RLock

DEFAULT_FEED = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"
_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
_NO_PROXY_VARIABLES = ("NO_PROXY", "no_proxy")
_ENV_LOCK = RLock()


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
