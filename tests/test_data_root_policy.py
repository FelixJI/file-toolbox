"""GUI/CLI 持久数据根的公共契约。"""

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


def test_gui_data_root_keeps_existing_home_data_in_place(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "profile"
    elsewhere = tmp_path / "install" / "current"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)

    with use_data_root_policy(GuiDataRootPolicy(home)):
        assert get_data_dir() == home / ".file_toolbox"
        assert get_backup_dir() == home / ".file_toolbox" / "backups"
        assert get_history_dir() == home / ".file_toolbox" / "history"
        assert get_log_dir() == home / ".file_toolbox" / "logs"


def test_frozen_gui_bootstrap_sets_home_policy_and_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    from file_toolbox.gui_entry import prepare_gui_runtime

    home = tmp_path / "profile"
    install = tmp_path / "FileToolbox" / "current"
    install.mkdir(parents=True)
    monkeypatch.chdir(install)

    with prepare_gui_runtime(frozen=True, home=home):
        assert Path.cwd() == home
        assert get_data_dir() == home / ".file_toolbox"


def test_development_gui_bootstrap_uses_home_policy_without_changing_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    from file_toolbox.gui_entry import prepare_gui_runtime

    home = tmp_path / "profile"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    with prepare_gui_runtime(frozen=False, home=home):
        assert Path.cwd() == workspace
        assert get_data_dir() == home / ".file_toolbox"
