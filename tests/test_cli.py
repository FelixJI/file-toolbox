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


# ---------------------------------------------------------------------------
# mkdir:--from-table 解析失败(parse_excel_table_data valid=False,行 26-28)
# ---------------------------------------------------------------------------


def test_mkdir_from_table_parse_invalid_errors(tmp_path):
    """--from-table 内容缺少 Tab 分隔 → parse_excel_table_data 返回 valid=False
    → 红字提示 + Exit(1)(行 27-28)。

    注:非法路径字符(* : 等)不会使 valid=False,只会记入 invalid_folders 后被替换
    (见 test_mkdir_from_table)。真正触发 valid=False 的是空文本或缺 Tab 分隔符。
    """
    table = tmp_path / "bad_structure.txt"
    # 整段无 Tab 分隔 → parse_excel_table_data 返回 valid=False
    table.write_text("部门A\n部门B\n", encoding="utf-8")
    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path), "--from-table", str(table)])
    assert r.exit_code == 1
    assert "错误" in r.output
    assert "Tab" in r.output


# ---------------------------------------------------------------------------
# mkdir:create_folders 失败(行 51-53)
# ---------------------------------------------------------------------------


def test_mkdir_create_folders_failure_errors(tmp_path, monkeypatch):
    """create_folders 返回 success=False → 红字打印 error_message + Exit(1)(行 51-53)。"""
    from file_toolbox.core.batch_mkdir import CreateResult, FolderCreatorService

    def fake_create(self, items, strategy, skip_callback=None, root=None, structure_count=None):
        return CreateResult(
            created_count=0,
            skipped_count=0,
            total_count=len(items),
            success=False,
            error_message="模拟创建失败:权限不足",
        )

    monkeypatch.setattr(FolderCreatorService, "create_folders", fake_create)

    r = runner.invoke(app, ["mkdir", "--root", str(tmp_path), "--levels", "部门A/项目1"])
    assert r.exit_code == 1
    assert "模拟创建失败:权限不足" in r.output


# ---------------------------------------------------------------------------
# replace:--yes 执行返回 errors(行 45-46)
# ---------------------------------------------------------------------------


def test_replace_execute_echoes_failures(tmp_path, monkeypatch):
    """--yes 执行,execute_replace 返回非空 errors → 每条失败被 echo(行 45-46)。"""
    from file_toolbox.core.batch_replace.service import ContentReplaceService

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")

    def fake_execute(
        self,
        files,
        operations,
        keep_new_format=False,
        progress_callback=None,
        cancel_check=None,
        keep_backup=True,
    ):
        # 与真实 execute_replace 形状一致:(success, total, errors)
        return 0, 0, ["文件被占用: a.txt"]

    monkeypatch.setattr(ContentReplaceService, "execute_replace", fake_execute)

    r = runner.invoke(
        app,
        ["replace", str(f), "--op", "simple_replace:find=hello,replace=world", "--yes"],
    )
    assert r.exit_code == 0, r.output
    # 失败行被 echo(行 46)
    assert "失败" in r.output
    assert "文件被占用: a.txt" in r.output


# ---------------------------------------------------------------------------
# pdf:batch_generate 返回失败 result(行 53-54)
# ---------------------------------------------------------------------------


def test_pdf_batch_generate_failure_echoes_error(tmp_path, monkeypatch):
    """batch_generate 返回 success=False 的 result → error 被 echo(行 53-54)。"""
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    # 源文件存在与否不影响(mock 接管 batch_generate),但创建一个保持真实
    src = tmp_path / "photo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG 魔数占位

    def fake_batch(self, files, config, progress_callback=None, cancel_check=None):
        return [
            {
                "source": src,
                "output": tmp_path / "photo.pdf",
                "success": False,
                "error": "模拟转换失败:引擎不可用",
            }
        ]

    monkeypatch.setattr(PDFGeneratorService, "batch_generate", fake_batch)

    r = runner.invoke(app, ["pdf", str(src)])
    assert r.exit_code == 0, r.output
    # 失败结果被标记 FAIL + error 被 echo(行 54)
    assert "FAIL" in r.output
    assert "模拟转换失败:引擎不可用" in r.output


def test_pdf_all_failure_exit_code_zero_currently(tmp_path, monkeypatch):
    """**全部**转换失败时,当前 pdf_cmd 仍 exit 0(锁定已知风险行为)。

    pdf_cmd 在 fail!=0 时仅用黄色打印汇总,不 raise typer.Exit(1)。这意味着 CI 脚本
    无法凭 exit code 判定失败。锁定当前行为:未来若改为「有失败即 exit 1」,
    该测试应变红提醒有意更新。
    """
    from file_toolbox.core.batch_pdf.service import PDFGeneratorService

    src = tmp_path / "a.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_batch(self, files, config, progress_callback=None, cancel_check=None):
        return [
            {
                "source": src,
                "output": tmp_path / "a.pdf",
                "success": False,
                "error": "全失败",
            }
        ]

    monkeypatch.setattr(PDFGeneratorService, "batch_generate", fake_batch)
    r = runner.invoke(app, ["pdf", str(src)])
    assert r.exit_code == 0  # 当前:全失败也 exit 0
    assert "成功 0, 失败 1" in r.output  # 汇总行精确文本
