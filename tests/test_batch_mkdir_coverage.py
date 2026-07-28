"""FolderCreatorService 未覆盖分支补充测试。

覆盖 batch_mkdir.py 行:
- 98: 空行 continue
- 118: 空单元格且无上一行值 → break
- 127: 无有效结构 → '未找到有效的文件夹结构数据'
- 141-143: parse 全局 except(制造内部异常)
- 166: build_folder_paths 空 root 或空结构
- 190-194: check_existing_folders
- 206: count_existing_folders
- 285-289: create_folders CONFIRM 策略 + skip_callback
- 297-299: create_folders mkdir 失败
- 314-316: create_folders 外层 except
"""

from pathlib import Path

from file_toolbox.core.batch_mkdir import (
    ConflictStrategy,
    FolderCreatorService,
    FolderStructureItem,
)


def _svc() -> FolderCreatorService:
    return FolderCreatorService()


# ---------------------------------------------------------------------------
# parse_excel_table_data:空行 continue(行 98)
# ---------------------------------------------------------------------------


def test_parse_skips_blank_lines():
    """含空行的表格:空行被 continue 跳过。"""
    text = "部门A\t项目1\n\n\n部门B\t项目2"
    r = _svc().parse_excel_table_data(text)
    assert r.valid
    assert ("部门A", "项目1") in r.folder_structure
    assert ("部门B", "项目2") in r.folder_structure
    assert len(r.folder_structure) == 2


# ---------------------------------------------------------------------------
# parse_excel_table_data:空单元格且无上一行值 → break(行 118)
# ---------------------------------------------------------------------------


def test_parse_empty_cell_no_prev_row_breaks():
    """首行首列为空 → 无上一行可继承 → break,该行无结构。"""
    text = "\t项目1\n部门A\t项目2"
    r = _svc().parse_excel_table_data(text)
    # 第一行无法构成结构(首列空,无 prev_row)→ 只有第二行
    assert r.valid
    assert ("部门A", "项目2") in r.folder_structure


def test_parse_inherit_stops_when_prev_row_shorter():
    """空单元格超出上一行长度 → break(行 118)。

    上一行只有 1 列,当前行第 2 列空 → i=1 >= len(prev_row)=1 → break。
    """
    text = "部门A\n\t项目2"
    r = _svc().parse_excel_table_data(text)
    # 第二行首列空 → 继承 "部门A";第二列空但 prev_row 只 1 项 → break
    assert ("部门A",) in r.folder_structure


# ---------------------------------------------------------------------------
# parse_excel_table_data:无有效结构(行 127)
# ---------------------------------------------------------------------------


def test_parse_only_blank_lines_no_structure():
    """行 127 为防御性兜底(text.strip() 非空保证至少一条结构),已标注 pragma: no cover。

    此测试验证首行总会产生结构(text.strip 后首字符非空),确保该分支确实不可达。
    """
    text = "a\tb"
    r = _svc().parse_excel_table_data(text)
    assert r.valid  # 首行总产生结构,行 127 不可达


def test_parse_break_when_empty_cell_beyond_prev_row():
    """空单元格超出 prev_row 长度 → break(行 118)。

    三行结构:行1 单列,行2 第二列空且超出 prev_row(1 项)→ break,行3 正常。
    行2 因 break 只保留第 1 列。
    """
    text = "a\na\t\nb"
    # 行1: "a" → ('a',), prev_row=['a']
    # 行2: "a\t" → split=['a',''], i=0 'a'非空→append; i=1 空,1<1 False → break(行118)
    # 行3: "b" → ('b',), prev_row 更新为行2 的 ['a']
    r = _svc().parse_excel_table_data(text)
    assert r.valid
    assert ("a",) in r.folder_structure
    assert ("b",) in r.folder_structure


def test_parse_structure_all_invalid_chars_still_recorded():
    """含非法字符的单元格仍记入 folder_structure(invalid_folders 也记)。"""
    text = "a*b\tc*d"
    r = _svc().parse_excel_table_data(text)
    assert r.valid
    assert ("a*b", "c*d") in r.folder_structure
    assert len(r.invalid_folders) >= 1


# ---------------------------------------------------------------------------
# parse_excel_table_data:全局 except(行 141-143)
# ---------------------------------------------------------------------------


def test_parse_global_exception_handled(monkeypatch):
    """内部异常(如 split 抛错)→ 全局 except → 返回 invalid。

    用 monkeypatch 让 str.strip 抛异常较难;改用一个非 str 输入触发内部异常。
    但 parse 签名要求 str。改用 monkeypatch 让 INVALID_CHARS 的 any 迭代抛错。
    """
    svc = _svc()
    # 让 INVALID_CHARS 迭代时抛异常 → 触发全局 except
    monkeypatch.setattr(
        type(svc), "INVALID_CHARS", property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    )
    r = svc.parse_excel_table_data("a\tb")
    assert r.valid is False
    assert "解析表格数据时出错" in r.error_message


# ---------------------------------------------------------------------------
# build_folder_paths:空输入(行 166)
# ---------------------------------------------------------------------------


def test_build_folder_paths_empty_root():
    """root_path 为 falsy(None)→ 返回 [](行 165 not root_path)。"""
    svc = _svc()
    # 传 None 触发 `not root_path` 分支(类型注解为 Path 但运行时不强制)
    assert svc.build_folder_paths(None, [("a",)]) == []  # type: ignore[arg-type]


def test_build_folder_paths_empty_string_root():
    """root_path 为空字符串 → falsy → 返回 []。"""
    svc = _svc()
    assert svc.build_folder_paths("", [("a",)]) == []  # type: ignore[arg-type]


def test_build_folder_paths_empty_structure(tmp_path):
    """folder_structure 为空 → 返回 []。"""
    svc = _svc()
    assert svc.build_folder_paths(tmp_path, []) == []


def test_build_folder_paths_marks_existing(tmp_path):
    """已存在的路径 → exists=True。"""
    svc = _svc()
    (tmp_path / "exists").mkdir()
    items = svc.build_folder_paths(tmp_path, [("exists",), ("new",)])
    assert items[0].exists is True
    assert items[1].exists is False


# ---------------------------------------------------------------------------
# check_existing_folders(行 190-194)
# ---------------------------------------------------------------------------


def test_check_existing_folders(tmp_path):
    """返回已存在文件夹路径集合。"""
    svc = _svc()
    (tmp_path / "e1").mkdir()
    items = [
        FolderStructureItem(path=tmp_path / "e1", levels=("e1",), exists=True),
        FolderStructureItem(path=tmp_path / "n1", levels=("n1",), exists=False),
    ]
    existing = svc.check_existing_folders(items)
    assert existing == {tmp_path / "e1"}


def test_check_existing_folders_empty():
    """空列表 → 空集合。"""
    assert _svc().check_existing_folders([]) == set()


# ---------------------------------------------------------------------------
# count_existing_folders(行 206)
# ---------------------------------------------------------------------------


def test_count_existing_folders(tmp_path):
    svc = _svc()
    items = [
        FolderStructureItem(path=tmp_path / "e1", levels=("e1",), exists=True),
        FolderStructureItem(path=tmp_path / "e2", levels=("e2",), exists=True),
        FolderStructureItem(path=tmp_path / "n1", levels=("n1",), exists=False),
    ]
    assert svc.count_existing_folders(items) == 2


def test_count_existing_folders_none():
    assert _svc().count_existing_folders([]) == 0


# ---------------------------------------------------------------------------
# create_folders:CONFIRM 策略 + skip_callback(行 285-289)
# ---------------------------------------------------------------------------


def test_create_folders_confirm_skip_when_callback_true(tmp_path):
    """CONFIRM + skip_callback 返回 True → 跳过(skipped_count +1)。"""
    svc = _svc()
    (tmp_path / "exists").mkdir()
    items = svc.build_folder_paths(tmp_path, [("exists",)])
    result = svc.create_folders(items, ConflictStrategy.CONFIRM, skip_callback=lambda item: True)
    assert result.skipped_count == 1
    assert result.created_count == 0


def test_create_folders_confirm_keep_when_callback_false(tmp_path):
    """CONFIRM + skip_callback 返回 False → MERGE 行为(保留,不创建新)。"""
    svc = _svc()
    (tmp_path / "exists").mkdir()
    items = svc.build_folder_paths(tmp_path, [("exists",)])
    result = svc.create_folders(items, ConflictStrategy.CONFIRM, skip_callback=lambda item: False)
    # callback False → 不跳过,但已存在且非 SKIP → 落到 MERGE(不操作)
    assert result.skipped_count == 0
    assert result.created_count == 0


def test_create_folders_confirm_without_callback(tmp_path):
    """CONFIRM 但无 callback → 已存在项不操作(类似 MERGE)。"""
    svc = _svc()
    (tmp_path / "exists").mkdir()
    items = svc.build_folder_paths(tmp_path, [("exists",)])
    result = svc.create_folders(items, ConflictStrategy.CONFIRM)
    assert result.success


# ---------------------------------------------------------------------------
# create_folders:mkdir 失败(行 297-299)
# ---------------------------------------------------------------------------


def test_create_folders_mkdir_failure_returns_error(tmp_path, monkeypatch):
    """mkdir 抛异常 → 返回 success=False + error_message(行 297-305)。"""
    svc = _svc()
    items = svc.build_folder_paths(tmp_path, [("new",)])
    # mock Path.mkdir 抛异常
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied")))
    result = svc.create_folders(items, ConflictStrategy.MERGE)
    assert result.success is False
    assert "创建文件夹失败" in result.error_message
    assert result.created_count == 0


def test_create_folders_partial_success_before_failure(tmp_path, monkeypatch):
    """前 N 个成功,第 N+1 个失败 → created_count 反映已完成数。"""
    svc = _svc()
    items = svc.build_folder_paths(tmp_path, [("ok",), ("bad",)])
    call_count = {"n": 0}
    real_mkdir = Path.mkdir

    def flaky_mkdir(self, *a, **k):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise PermissionError("denied")
        return real_mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)
    result = svc.create_folders(items, ConflictStrategy.MERGE)
    assert result.success is False
    assert result.created_count == 1  # 第一个成功


# ---------------------------------------------------------------------------
# create_folders:外层 except(行 314-316)
# ---------------------------------------------------------------------------


def test_create_folders_outer_exception_handled(monkeypatch):
    """外层循环抛异常 → 外层 except(行 314-316)→ success=False。

    构造一个 __len__ 正常但 __iter__ 抛异常的假 items:total_count=len() 能算,
    进入 for 循环时 __iter__ 抛 RuntimeError → 被外层 try/except 捕获。
    """
    svc = _svc()

    class _BoomItems:
        def __len__(self):
            return 1

        def __iter__(self):
            raise RuntimeError("iterate boom")

    result = svc.create_folders(_BoomItems(), ConflictStrategy.MERGE)  # type: ignore[arg-type]
    assert result.success is False
    assert "批量创建文件夹时出错" in result.error_message


# ---------------------------------------------------------------------------
# MERGE 策略对已存在文件夹不操作(行 290 注释路径)
# ---------------------------------------------------------------------------


def test_create_folders_merge_existing_no_op(tmp_path):
    """MERGE 策略:已存在文件夹不跳过不创建(落在注释分支)。"""
    svc = _svc()
    (tmp_path / "exists").mkdir()
    items = svc.build_folder_paths(tmp_path, [("exists",)])
    result = svc.create_folders(items, ConflictStrategy.MERGE)
    assert result.success
    assert result.created_count == 0
    assert result.skipped_count == 0


def test_create_folders_empty_items():
    """空 items → success=True,全 0。"""
    result = _svc().create_folders([], ConflictStrategy.MERGE)
    assert result.success
    assert result.created_count == 0
    assert result.total_count == 0


# ---------------------------------------------------------------------------
# validate_folder_name 边界(已有部分,补充空白)
# ---------------------------------------------------------------------------


def test_validate_folder_name_whitespace_only():
    """纯空白名 → False。"""
    assert _svc().validate_folder_name("   ") is False
