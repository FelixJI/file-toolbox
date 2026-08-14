"""更新 transport 的候选与 forward proxy 契约。"""

from file_toolbox.updater.transport import (
    build_feed_candidates,
    forward_proxy_environment,
)


def test_prefix_candidates_preserve_order_and_end_with_direct_feed() -> None:
    direct = "https://github.com/FelixJI/file-toolbox/releases/latest/download/"

    assert build_feed_candidates(["https://one.example", "https://two.example/"]) == (
        f"https://one.example/{direct}",
        f"https://two.example/{direct}",
        direct,
    )


def test_forward_proxy_environment_sets_both_cases_and_restores(monkeypatch) -> None:
    import os

    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://before.invalid")

    with forward_proxy_environment("http://127.0.0.1:8899"):
        assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:8899"
        assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:8899"
        assert os.environ["http_proxy"] == "http://127.0.0.1:8899"
        assert os.environ["https_proxy"] == "http://127.0.0.1:8899"
        assert os.environ["NO_PROXY"] == ""
        assert os.environ["no_proxy"] == ""

    assert os.environ["HTTP_PROXY"] == "http://before.invalid"
    if os.name == "nt":
        assert os.environ["http_proxy"] == "http://before.invalid"
    else:
        assert "http_proxy" not in os.environ
