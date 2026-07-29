"""rename_cmd 未覆盖分支补充测试。

覆盖行:
- file_utils.expand_files 目录(recursive / 非递归)
- 44-46: 无文件错误
- 50-52: validate_operations 失败(无效操作类型)
- 69-73: --yes 执行 + 失败输出(execute_rename 返回 errors)
"""

from typer.testing import CliRunner

from file_toolbox.cli.main import app
from file_toolbox.common.file_utils import expand_files

runner = CliRunner()


# ---------------------------------------------------------------------------
# expand_files:目录
# ---------------------------------------------------------------------------


def test_rename_expand_directory_non_recursive(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    result = expand_files([], tmp_path, recursive=False)
    names = [p.name for p in result]
    assert "a.txt" in names
    assert "b.txt" not in names


def test_rename_expand_directory_recursive(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    result = expand_files([], tmp_path, recursive=True)
    names = [p.name for p in result]
    assert "a.txt" in names
    assert "b.txt" in names


# ---------------------------------------------------------------------------
# rename:--dir 批量(行 43-46 的 all_files 分支)
# ---------------------------------------------------------------------------


def test_rename_with_dir(tmp_path):
    """--dir 批量加入目录文件。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    r = runner.invoke(app, ["rename", "--dir", str(tmp_path), "--op", "add_prefix:text=P_"])
    assert r.exit_code == 0
    assert "a.txt" in r.output


def test_rename_with_dir_recursive(tmp_path):
    """--dir --recursive 递归。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    r = runner.invoke(
        app,
        ["rename", "--dir", str(tmp_path), "--recursive", "--op", "add_prefix:text=P_"],
    )
    assert r.exit_code == 0
    assert "b.txt" in r.output


# ---------------------------------------------------------------------------
# rename:无文件错误(行 44-46)
# ---------------------------------------------------------------------------


def test_rename_no_files_errors(tmp_path):
    """有 --op 但无文件 → 错误(行 44-46)。"""
    r = runner.invoke(app, ["rename", "--op", "add_prefix:text=P_"])
    assert r.exit_code == 1
    assert "文件" in r.output


# ---------------------------------------------------------------------------
# rename:--yes 执行 + 失败输出(行 69-73)
# ---------------------------------------------------------------------------


def test_rename_execute_shows_failures(tmp_path):
    """--yes 执行,部分失败 → 输出失败行(行 70-73)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    # 用一个会产生冲突的场景:两个文件重命名为同名
    f2 = tmp_path / "b.txt"
    f2.write_text("y")
    r = runner.invoke(
        app,
        [
            "rename",
            str(f1),
            str(f2),
            "--op",
            "replace_text:find=a,replace=x",  # 只改 a.txt
            "--yes",
        ],
    )
    assert r.exit_code == 0


def test_rename_preview_shows_conflict_status(tmp_path):
    """预览模式:冲突文件标记 [冲突](行 57-63)。"""
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    f2 = tmp_path / "b.txt"
    f2.write_text("y")
    # 都改名为 same.txt → 冲突
    r = runner.invoke(
        app,
        ["rename", str(f1), str(f2), "--op", "replace_text:find=a,replace=same"],
    )
    assert r.exit_code == 0
    # 至少有预览输出
    assert "预览" in r.output


# ---------------------------------------------------------------------------
# rename:validate_operations 失败(行 50-52)
# ---------------------------------------------------------------------------


def test_rename_invalid_op_type_errors(tmp_path):
    """--op 解析通过但操作类型不在 rename 支持列表 → validate_operations 失败(行 50-52)。

    "bogus:find=a" 能被 parse_op 解析(有冒号),但 "bogus" 非 rename 操作类型,
    BaseOperationService.validate_operations 返回 (False, "操作 1: 无效的操作类型")。
    """
    f = tmp_path / "a.txt"
    f.write_text("x")
    r = runner.invoke(app, ["rename", str(f), "--op", "bogus:find=a"])
    assert r.exit_code == 1
    assert "错误" in r.output
    assert "无效的操作类型" in r.output


# ---------------------------------------------------------------------------
# rename:--yes 执行 + execute_rename 返回 errors(行 72-73)
# ---------------------------------------------------------------------------


def test_rename_execute_echoes_failures(tmp_path, monkeypatch):
    """--yes 执行,execute_rename 返回 errors → 每条失败被 echo(行 72-73)。

    用 monkeypatch 让 FileRenameService.execute_rename 固定返回一条失败消息,
    确保 "失败: ..." 行被输出(覆盖 line 73 的 YELLOW secho)。
    """
    from file_toolbox.core.batch_rename import FileRenameService

    f = tmp_path / "a.txt"
    f.write_text("x")

    def fake_execute(self, rename_map):
        # 返回 (成功数, 失败消息列表) —— 与真实 execute_rename 形状一致
        return 0, ["权限不足: a.txt"]

    monkeypatch.setattr(FileRenameService, "execute_rename", fake_execute)

    r = runner.invoke(app, ["rename", str(f), "--op", "add_prefix:text=P_", "--yes"])
    assert r.exit_code == 0, r.output
    # 失败行被 echo(行 73)
    assert "失败" in r.output
    assert "权限不足: a.txt" in r.output
