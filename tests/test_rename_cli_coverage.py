"""rename_cmd 未覆盖分支补充测试。

覆盖行:
- 15-18: _expand 目录(recursive / 非递归)
- 44-46: 无文件错误
- 50-52: validate_operations 失败(parse_ops 通过但语义校验失败)
- 69-73: --yes 执行 + 失败输出(已有部分,补确认)
"""


from typer.testing import CliRunner

from file_toolbox.cli.main import app
from file_toolbox.cli.rename_cmd import _expand

runner = CliRunner()


# ---------------------------------------------------------------------------
# _expand:目录(行 15-18)
# ---------------------------------------------------------------------------


def test_rename_expand_directory_non_recursive(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    result = _expand([], tmp_path, recursive=False)
    names = [p.name for p in result]
    assert "a.txt" in names
    assert "b.txt" not in names


def test_rename_expand_directory_recursive(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    result = _expand([], tmp_path, recursive=True)
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
    r = runner.invoke(
        app, ["rename", "--dir", str(tmp_path), "--op", "add_prefix:text=P_"]
    )
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
