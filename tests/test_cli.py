import re

from typer.testing import CliRunner

from file_toolbox import __version__
from file_toolbox.cli.main import app

runner = CliRunner()


def test_version():
    """--version 输出应与 package 实际 __version__ 一致(不硬编码字面量,避免发版即坏)。"""
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert r.output.strip() == __version__
    # 且形如 x.y.z 的稳定版本号(而非回退占位 "0.0.0+unknown")
    assert re.fullmatch(r"\d+\.\d+\.\d+", r.output.strip())


def test_help_lists_commands():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ["rename", "mkdir", "pdf", "replace", "gui", "invoice"]:
        assert cmd in r.output


def test_rename_no_op_errors(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f)])
    assert r.exit_code == 1
    assert "--op" in r.output


def test_rename_preview(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=PRE_"])
    assert r.exit_code == 0
    assert "PRE_report.txt" in r.output
    assert "预览模式" in r.output


def test_rename_execute(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=PRE_", "--yes"])
    assert r.exit_code == 0
    assert (tmp_path / "PRE_report.txt").exists()


def test_mkdir_from_levels(tmp_path):
    r = runner.invoke(
        app,
        ["mkdir", "--root", str(tmp_path), "--levels", "部门A/项目1", "--levels", "部门A/项目2"],
    )
    assert r.exit_code == 0
    assert (tmp_path / "部门A" / "项目1").is_dir()
    assert (tmp_path / "部门A" / "项目2").is_dir()


def test_mkdir_replaces_special_chars(tmp_path):
    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path), "--levels", "a*b"])
    assert r.exit_code == 0
    assert (tmp_path / "a_b").is_dir()


def test_no_subcommand_shows_help():
    """无子命令 → 输出总 help(覆盖 main_callback 的 invoked_subcommand is None 分支)。"""
    r = runner.invoke(app, [])
    assert r.exit_code == 0
    # 帮助文本应列出命令
    assert "rename" in r.output
    assert "批量" in r.output or "file-toolbox" in r.output


def test_mkdir_from_table(tmp_path):
    """--from-table:从 Tab 分隔文本读结构批量建文件夹(列即层级,含特殊字符被替换)。"""
    table = tmp_path / "structure.txt"
    # 每行 Tab 分列,列即层级;含特殊字符 * 会替换为 _
    table.write_text("部门A*\t项目1\n部门B\t项目2\n", encoding="utf-8")
    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path / "out"), "--from-table", str(table)])
    assert r.exit_code == 0
    # * 被替换为 _ → 部门A_/项目1
    assert (tmp_path / "out" / "部门A_" / "项目1").is_dir()
    assert (tmp_path / "out" / "部门B" / "项目2").is_dir()
    # 提示无效字符被替换
    assert "无效字符" in r.output


def test_mkdir_no_levels_errors(tmp_path):
    """无 --levels 也无 --from-table → 退出码 1。"""
    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path)])
    assert r.exit_code == 1
    assert "层级" in r.output or "levels" in r.output.lower()


def test_mkdir_on_conflict_skip(tmp_path):
    """--on-conflict skip:已存在目录不合并创建子项。"""
    # 预先建好父目录
    (tmp_path / "existing").mkdir()
    r = runner.invoke(
        app,
        [
            "mkdir",
            "--root",
            str(tmp_path),
            "--levels",
            "existing/sub",
            "--on-conflict",
            "skip",
        ],
    )
    # skip 策略:existing 已存在,跳过(不报错)
    assert r.exit_code == 0
    assert "跳过" in r.output or "完成" in r.output
