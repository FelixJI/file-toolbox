"""replace 命令端到端测试(CliRunner)。

仅用 .txt 输入走 TextHandler(纯 Python),全程不触碰 Word/Excel COM,Linux CI 可跑通。
覆盖 cli/replace_cmd.py 全部分支:help、参数校验、预览、执行、备份。
"""

from pathlib import Path

from typer.testing import CliRunner

from file_toolbox.cli.main import app

runner = CliRunner()


def _ensure(d: Path) -> Path:
    """重定向备份目录到临时路径并自动创建(复刻真实 get_backup_dir 的建目录语义)。"""
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_replace_help_lists():
    """--help 输出命令说明。"""
    r = runner.invoke(app, ["replace", "--help"])
    assert r.exit_code == 0
    assert "替换" in r.output or "replace" in r.output.lower()


def test_replace_no_op_errors(tmp_path):
    """无 --op → 退出码 1 + 错误提示。"""
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    r = runner.invoke(app, ["replace", str(f)])
    assert r.exit_code == 1
    assert "--op" in r.output


def test_replace_no_files_errors(tmp_path):
    """有 --op 但无文件 → 退出码 1。"""
    r = runner.invoke(app, ["replace", "--op", "simple_replace:find=a"])
    assert r.exit_code == 1
    assert "文件" in r.output


def test_replace_invalid_op_errors(tmp_path):
    """无效操作类型(校验失败)→ 退出码 1。"""
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    r = runner.invoke(app, ["replace", str(f), "--op", "bogus_type:find=a"])
    assert r.exit_code == 1


def test_replace_regex_invalid_pattern_errors(tmp_path):
    """regex_replace 给非法正则 → 校验失败退出码 1。"""
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    r = runner.invoke(app, ["replace", str(f), "--op", "regex_replace:pattern=[", "find=a"])
    assert r.exit_code == 1


def test_replace_preview_does_not_modify(tmp_path):
    """预览模式(无 --yes):输出匹配数,不改文件内容。"""
    f = tmp_path / "a.txt"
    f.write_text("旧公司 旧公司", encoding="utf-8")
    r = runner.invoke(app, ["replace", str(f), "--op", "simple_replace:find=旧公司,replace=新公司"])
    assert r.exit_code == 0
    assert "2" in r.output  # 匹配数
    # 未加 --yes,文件内容不变
    assert f.read_text(encoding="utf-8") == "旧公司 旧公司"


def test_replace_execute_modifies_and_backs_up(tmp_path, monkeypatch):
    """--yes 执行:txt 内容被替换 + 生成备份。"""
    # 把备份目录重定向到临时目录(并创建),避免污染真实 .file_toolbox/backups
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: _ensure(backup_dir)
    )

    f = tmp_path / "a.txt"
    f.write_text("旧公司 旧公司", encoding="utf-8")
    r = runner.invoke(
        app,
        [
            "replace",
            str(f),
            "--op",
            "simple_replace:find=旧公司,replace=新公司",
            "--yes",
        ],
    )
    assert r.exit_code == 0, r.output
    assert f.read_text(encoding="utf-8") == "新公司 新公司"
    # 备份目录有 1 个 .txt 备份
    backups = list(backup_dir.glob("*.txt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "旧公司 旧公司"


def test_replace_regex_execute(tmp_path, monkeypatch):
    """--yes 执行 regex_replace:正则替换生效,含纯数字替换串。

    回归:op_parser._coerce 会把裸数字值(如 replace=2026)强转为 int,
    导致 re.subn(text, 2026) 报 TypeError。find/replace 应保持字符串语义。
    """
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: _ensure(backup_dir)
    )

    f = tmp_path / "nums.txt"
    f.write_text("2024 和 2025", encoding="utf-8")
    r = runner.invoke(
        app,
        ["replace", str(f), "--op", r"regex_replace:pattern=20\d{2},replace=2026", "--yes"],
    )
    assert r.exit_code == 0, r.output
    assert f.read_text(encoding="utf-8") == "2026 和 2026"


def test_replace_case_sensitive(tmp_path, monkeypatch):
    """case_sensitive=true:大小写敏感替换(只换匹配大小写的)。"""
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: _ensure(backup_dir)
    )

    f = tmp_path / "c.txt"
    f.write_text("ABC abc ABC", encoding="utf-8")
    r = runner.invoke(
        app,
        [
            "replace",
            str(f),
            "--op",
            "simple_replace:find=ABC,replace=X,case_sensitive=true",
            "--yes",
        ],
    )
    assert r.exit_code == 0, r.output
    # 大小写敏感:只替换大写 ABC(2 处),保留 abc
    assert f.read_text(encoding="utf-8") == "X abc X"


def test_replace_keep_backup_flag_accepted(tmp_path, monkeypatch):
    """--keep-backup(默认):执行替换并生成备份文件。"""
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: _ensure(backup_dir)
    )

    f = tmp_path / "a.txt"
    f.write_text("foo", encoding="utf-8")
    r = runner.invoke(
        app,
        [
            "replace",
            str(f),
            "--op",
            "simple_replace:find=foo,replace=bar",
            "--keep-backup",
            "--yes",
        ],
    )
    assert r.exit_code == 0, r.output
    assert f.read_text(encoding="utf-8") == "bar"
    # 默认保留备份
    assert len(list(backup_dir.glob("*.txt"))) == 1


def test_replace_no_backup_flag_skips_backup(tmp_path, monkeypatch):
    """--no-backup:执行替换但不生成备份文件。

    回归:此前 replace_cmd 接收 keep_backup 但未透传给 execute_replace,
    导致 --no-backup 实际仍备份。修复后应真正跳过备份。
    """
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        "file_toolbox.core.batch_replace.service.get_backup_dir", lambda: _ensure(backup_dir)
    )

    f = tmp_path / "a.txt"
    f.write_text("foo", encoding="utf-8")
    r = runner.invoke(
        app,
        ["replace", str(f), "--op", "simple_replace:find=foo,replace=bar", "--no-backup", "--yes"],
    )
    assert r.exit_code == 0, r.output
    assert f.read_text(encoding="utf-8") == "bar"
    # --no-backup 不生成备份
    assert len(list(backup_dir.glob("*.txt"))) == 0
