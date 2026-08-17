"""GUI/CLI 持久数据根的公共契约。"""

import sys
from pathlib import Path

from file_toolbox.common.paths import (
    CliDataRootPolicy,
    GuiDataRootPolicy,
    get_backup_dir,
    get_data_dir,
    get_history_dir,
    get_log_dir,
    use_data_root_policy,
)


def test_cli_data_root_follows_each_callers_working_directory(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    with use_data_root_policy(CliDataRootPolicy()):
        monkeypatch.chdir(first)
        assert get_data_dir() == first / ".file_toolbox"
        monkeypatch.chdir(second)
        assert get_data_dir() == second / ".file_toolbox"


def test_gui_data_root_follows_program_directory(tmp_path: Path, monkeypatch) -> None:
    program = tmp_path / "FileToolbox"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with use_data_root_policy(GuiDataRootPolicy(program)):
        assert get_data_dir() == program / ".file_toolbox"
        assert get_backup_dir() == program / ".file_toolbox" / "backups"
        assert get_history_dir() == program / ".file_toolbox" / "history"
        assert get_log_dir() == program / ".file_toolbox" / "logs"


def test_program_dir_source_run_is_repo_root(monkeypatch) -> None:
    import file_toolbox
    from file_toolbox.gui_entry import _program_dir

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert _program_dir() == Path(file_toolbox.__file__).resolve().parent.parent


def test_program_dir_frozen_plain_onedir(tmp_path: Path, monkeypatch) -> None:
    from file_toolbox.gui_entry import _program_dir

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "dist" / "FileToolbox" / "FileToolbox.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    assert _program_dir() == exe.parent


def test_program_dir_frozen_velopack_current_dir(tmp_path: Path, monkeypatch) -> None:
    """Velopack 便携布局:exe 在 <root>/current/ 下,数据根须避开被更新替换的 current/。"""
    from file_toolbox.gui_entry import _program_dir

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "FileToolbox" / "current" / "FileToolbox.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    assert _program_dir() == tmp_path / "FileToolbox"


def test_frozen_gui_bootstrap_pins_program_data_root_and_home_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    from file_toolbox.gui_entry import prepare_gui_runtime

    home = tmp_path / "profile"
    program = tmp_path / "FileToolbox"
    install = program / "current"
    install.mkdir(parents=True)
    monkeypatch.chdir(install)

    with prepare_gui_runtime(frozen=True, program_dir=program, home=home):
        assert Path.cwd() == home
        assert get_data_dir() == program / ".file_toolbox"
    assert Path.cwd() == install


def test_development_gui_bootstrap_uses_program_policy_without_changing_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    from file_toolbox.gui_entry import prepare_gui_runtime

    home = tmp_path / "profile"
    program = tmp_path / "source" / "file-toolbox"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    with prepare_gui_runtime(frozen=False, program_dir=program, home=home):
        assert Path.cwd() == workspace
        assert get_data_dir() == program / ".file_toolbox"
