"""打包形态判定与 GUI 入口 Velopack hook 的回归契约。

历史 bug(0.2.9-0.2.11):Nuitka standalone 不设置 ``sys.frozen``、
``sys.executable`` 合成为 dist 内并不存在的 ``python.exe``。仅凭 ``sys.frozen``
的 gate 把 Nuitka 便携包当成源码运行:Velopack hook 被跳过,更新器的
``--veloapp-obsolete``/``--veloapp-updated`` hook 进程把整个 GUI 拉起来、15s
超时被强杀;启动自动检查更新也从未运行。
"""

import sys
import types

import pytest


def _plain_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 ``__main__`` 换成无 Nuitka 标记的干净模块(pytest 自身入口不可控)。"""

    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))


def _nuitka_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟 Nuitka:入口模块带 ``__compiled__`` 标记、不设置 ``sys.frozen``。"""

    main = types.ModuleType("__main__")
    main.__compiled__ = {"version": "test"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "__main__", main)


class TestIsPackagedRuntime:
    @pytest.mark.parametrize(
        ("make_main", "frozen"),
        [
            (_plain_main, None),  # 源码运行
            (_plain_main, False),  # 显式未冻结
        ],
    )
    def test_source_run_is_not_packaged(self, monkeypatch, make_main, frozen):
        from file_toolbox.common.runtime import is_packaged_runtime

        make_main(monkeypatch)
        if frozen is None:
            monkeypatch.delattr(sys, "frozen", raising=False)
        else:
            monkeypatch.setattr(sys, "frozen", frozen, raising=False)
        assert is_packaged_runtime() is False

    def test_pyinstaller_frozen_flag_is_packaged(self, monkeypatch):
        from file_toolbox.common.runtime import is_packaged_runtime

        _plain_main(monkeypatch)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert is_packaged_runtime() is True

    def test_nuitka_compiled_main_is_packaged_without_sys_frozen(self, monkeypatch):
        """Nuitka standalone 回归:Nuitka 不设 sys.frozen,信号是 __main__.__compiled__。"""

        from file_toolbox.common.runtime import is_packaged_runtime

        _nuitka_main(monkeypatch)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert is_packaged_runtime() is True


class _FakeVelopackApp:
    instances: list["_FakeVelopackApp"] = []

    def __init__(self) -> None:
        self.run_calls = 0
        _FakeVelopackApp.instances.append(self)

    def run(self) -> None:
        self.run_calls += 1


class TestRunVelopackHooks:
    def _install_fake_velopack(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeVelopackApp.instances = []
        monkeypatch.setitem(sys.modules, "velopack", types.SimpleNamespace(App=_FakeVelopackApp))

    def test_pyinstaller_runs_hooks(self, monkeypatch):
        from file_toolbox.gui_entry import _run_velopack_hooks

        self._install_fake_velopack(monkeypatch)
        _plain_main(monkeypatch)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert _run_velopack_hooks() is True
        assert [app.run_calls for app in _FakeVelopackApp.instances] == [1]

    def test_nuitka_runs_hooks_without_sys_frozen(self, monkeypatch):
        """Nuitka 回归:0.2.9-0.2.11 此路径被旧 gate(sys.frozen)跳过。"""

        from file_toolbox.gui_entry import _run_velopack_hooks

        self._install_fake_velopack(monkeypatch)
        _nuitka_main(monkeypatch)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert _run_velopack_hooks() is True
        assert [app.run_calls for app in _FakeVelopackApp.instances] == [1]

    def test_source_run_skips_hooks_without_importing_velopack(self, monkeypatch):
        from file_toolbox.gui_entry import _run_velopack_hooks

        # sys.modules[name] = None 表示"该模块不可用";若实现误 import 会抛 ImportError
        monkeypatch.setitem(sys.modules, "velopack", None)
        _plain_main(monkeypatch)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert _run_velopack_hooks() is False
