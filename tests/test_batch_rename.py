from pathlib import Path

from file_toolbox.core.batch_rename import FileRenameService


def _svc():
    return FileRenameService()


def test_get_operation_types():
    types = _svc().get_operation_types()
    assert "add_prefix" in types
    assert "regex_replace" in types


def test_apply_prefix(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("x")
    svc = _svc()
    result = svc.apply_operations([f], [{"type": "add_prefix", "params": {"text": "PRE_"}}])
    new_path, status = result[f]
    assert new_path.name == "PRE_report.txt"
    assert "准备" in status


def test_apply_suffix(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    result = _svc().apply_operations([f], [{"type": "add_suffix", "params": {"text": "_SUF"}}])
    assert result[f][0].name == "a_SUF.txt"


def test_apply_replace_text_case_insensitive(tmp_path):
    f = tmp_path / "HelloWorld.txt"
    f.write_text("x")
    result = _svc().apply_operations(
        [f], [{"type": "replace_text", "params": {"find": "hello", "replace": "hi"}}]
    )
    assert result[f][0].name == "hiWorld.txt"


def test_apply_regex_replace(tmp_path):
    f = tmp_path / "2023_report.txt"
    f.write_text("x")
    result = _svc().apply_operations(
        [f], [{"type": "regex_replace", "params": {"pattern": r"\d+", "replace": "2026"}}]
    )
    assert result[f][0].name == "2026_report.txt"


def test_apply_add_number_bracket(tmp_path):
    files = [(tmp_path / f"{i}.txt") for i in range(2)]
    for f in files:
        f.write_text("x")
    result = _svc().apply_operations(
        files, [{"type": "add_number", "params": {"start": 1, "digits": 3}}]
    )
    names = sorted(result[f][0].name for f in files)
    # start=1: 第一个文件 [001], 第二个文件 [002](序号随索引递增)
    assert names == ["0[001].txt", "1[002].txt"]


def test_apply_delete_chars_prefix(tmp_path):
    f = tmp_path / "ABCDE.txt"
    f.write_text("x")
    result = _svc().apply_operations(
        [f], [{"type": "delete_chars", "params": {"delete_type": "prefix", "value": "2"}}]
    )
    assert result[f][0].name == "CDE.txt"


def test_apply_add_date(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("x")
    result = _svc().apply_operations(
        [f], [{"type": "add_date", "params": {"format": "%Y", "position": "end"}}]
    )
    name = result[f][0].name
    assert name.startswith("x") and name[1:5].isdigit()


def test_apply_multiple_operations_chain(tmp_path):
    f = tmp_path / "draft.txt"
    f.write_text("x")
    result = _svc().apply_operations(
        [f],
        [
            {"type": "replace_text", "params": {"find": "draft", "replace": "final"}},
            {"type": "add_prefix", "params": {"text": "P_"}},
        ],
    )
    assert result[f][0].name == "P_final.txt"


def test_apply_conflict_detection(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    (tmp_path / "b.txt").write_text("y")
    result = _svc().apply_operations(
        [f], [{"type": "replace_text", "params": {"find": "a", "replace": "b"}}]
    )
    assert "冲突" in result[f][1]


def test_apply_intra_batch_collision_both_target_same_path(tmp_path):
    """批内两个文件映射到同一目标:当前实现仅检测与**已存在**文件冲突,不检测批内互撞,
    故两者都报「就绪」(execute 时第二个会撞已存在)。**锁定当前行为**:两目标路径相同。

    此为已知限制(检测批内冲突需额外逻辑)。锁定它,使未来若新增批内冲突检测,
    该测试会变红提醒有意更新预期。
    """
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("x")
    b.write_text("y")
    result = _svc().apply_operations(
        [a, b],
        [
            {"type": "replace_text", "params": {"find": "a", "replace": "x"}},
            {"type": "replace_text", "params": {"find": "b", "replace": "x"}},
        ],
    )
    assert result[a][0] == result[b][0]  # 同一目标路径 x.txt
    # 两者当前都报就绪(批内冲突未检测)
    assert "准备" in result[a][1]
    assert "准备" in result[b][1]


def test_execute_rename(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    svc = _svc()
    result = svc.apply_operations([f], [{"type": "add_prefix", "params": {"text": "P_"}}])
    new = result[f][0]
    count, errors = svc.execute_rename({f: new})
    assert count == 1
    assert not errors
    assert new.exists()
    assert not f.exists()


def test_validate_params_empty_prefix():
    ok, msg = _svc()._validate_params({"type": "add_prefix", "params": {"text": ""}}, 0)
    assert ok is False


def test_validate_params_bad_regex():
    ok, msg = _svc()._validate_params(
        {"type": "regex_replace", "params": {"pattern": "(", "replace": ""}}, 0
    )
    assert ok is False


# ---------------------------------------------------------------------------
# _validate_add_number (custom 校验函数覆盖)
# ---------------------------------------------------------------------------


def test_validate_add_number_digits_zero_invalid():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"digits": 0}}, 0)
    assert ok is False
    assert "位数" in msg


def test_validate_add_number_digits_negative_invalid():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"digits": -2}}, 1)
    assert ok is False


def test_validate_add_number_custom_empty_template():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"format": "custom", "custom_template": ""}}, 0)
    assert ok is False
    assert "模板" in msg


def test_validate_add_number_custom_missing_n_placeholder():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"format": "custom", "custom_template": "NOX"}}, 0)
    assert ok is False
    assert "占位符" in msg


def test_validate_add_number_custom_valid():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"format": "custom", "custom_template": "No-{n}"}}, 0)
    assert ok is True


def test_validate_add_number_non_digit_value():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"digits": "abc"}}, 0)
    assert ok is False
    assert "数字" in msg


def test_validate_add_number_ok_default():
    from file_toolbox.core.batch_rename import _validate_add_number

    ok, msg = _validate_add_number({"params": {"start": 1, "digits": 3}}, 0)
    assert ok is True


# ---------------------------------------------------------------------------
# _apply_single_operation 分支覆盖(直接调用,避免文件 IO)
# ---------------------------------------------------------------------------


def test_apply_single_unknown_op_returns_name_unchanged():
    svc = _svc()
    assert svc._apply_single_operation("name", ".txt", {"type": "bogus"}, 0, 1) == "name"


def test_replace_text_case_sensitive_branch():
    svc = _svc()
    out = svc._replace_text(
        "Hello hello", {"find": "Hello", "replace": "Hi", "case_sensitive": True}
    )
    assert out == "Hi hello"


def test_replace_text_empty_find_returns_name():
    svc = _svc()
    assert svc._replace_text("abc", {"find": "", "replace": "x"}) == "abc"


def test_regex_replace_empty_pattern_returns_name():
    svc = _svc()
    assert svc._regex_replace("abc", {"pattern": "", "replace": "x"}) == "abc"


def test_regex_replace_bad_pattern_returns_name():
    svc = _svc()
    assert svc._regex_replace("abc", {"pattern": "(", "replace": "x"}) == "abc"


def test_regex_replace_ignore_case_flag():
    svc = _svc()
    out = svc._regex_replace("AbC", {"pattern": "abc", "replace": "X", "ignore_case": True})
    assert out == "X"


def test_regex_replace_case_sensitive_default():
    svc = _svc()
    assert svc._regex_replace("AbC", {"pattern": "abc", "replace": "X"}) == "AbC"


# ---------------------------------------------------------------------------
# _replace_text:不区分大小写分支对 replacement 含反斜杠的处理(B3 回归)
# ---------------------------------------------------------------------------


def test_replace_text_case_insensitive_backslash_replace_matches_sensitive():
    r"""不区分大小写时,replacement 含字面反斜杠应与区分大小写分支行为一致。

    回归:旧实现 case-insensitive 分支用 pattern.sub(replace_text, name),
    re 把 replacement 当模板解释 —— replace 含 \d / \1 等会抛 re.error('bad escape'),
    或把 \1 当反向引用。而 case-sensitive 分支用 str.replace 视为字面量。
    两分支语义必须一致:replacement 在 simple_replace 中是字面文本。
    """
    svc = _svc()
    sensitive = svc._replace_text("abc", {"find": "a", "replace": r"x\d", "case_sensitive": True})
    insensitive = svc._replace_text(
        "abc", {"find": "a", "replace": r"x\d", "case_sensitive": False}
    )
    assert sensitive == "x\\dbc"
    assert insensitive == sensitive  # 两分支字面一致,不抛 re.error


# ---------------------------------------------------------------------------
# _add_number 各格式与位置分支
# ---------------------------------------------------------------------------


def test_add_number_format_parenthesis():
    svc = _svc()
    assert svc._add_number("f", {"format": "parenthesis", "digits": 2}, 0) == "f(01)"


def test_add_number_format_underscore():
    svc = _svc()
    assert svc._add_number("f", {"format": "underscore", "digits": 2}, 0) == "f_01"


def test_add_number_format_dash():
    svc = _svc()
    assert svc._add_number("f", {"format": "dash", "digits": 2}, 0) == "f-01"


def test_add_number_format_none():
    svc = _svc()
    assert svc._add_number("f", {"format": "none", "digits": 2}, 0) == "f01"


def test_add_number_format_custom():
    svc = _svc()
    assert (
        svc._add_number("f", {"format": "custom", "custom_template": "N{n}", "digits": 2}, 0)
        == "fN01"
    )


def test_add_number_format_unknown_falls_back():
    svc = _svc()
    # digits=2 → number_str="01"(index 0 → number 1);未知 format 走 formatted=number_str
    assert svc._add_number("f", {"format": "weird", "digits": 2}, 0) == "f01"


def test_add_number_position_start():
    svc = _svc()
    # position=start,format 默认 bracket → [01]
    assert svc._add_number("f", {"position": "start", "digits": 2}, 0) == "[01]f"


# ---------------------------------------------------------------------------
# _add_date 各分支(file source / position)
# ---------------------------------------------------------------------------


def test_add_date_position_start_current_source():
    svc = _svc()
    out = svc._add_date("f", {"format": "%Y", "position": "start", "source": "current"})
    assert out.endswith("f") and out[:-1].isdigit()


def test_add_date_file_source_existing_file(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("y")
    svc = _svc()
    out = svc._add_date("f", {"format": "%Y", "source": "file"}, f)
    assert out.startswith("f") and out[1:].isdigit()


def test_add_date_file_source_missing_file_falls_back_to_now(tmp_path):
    missing = tmp_path / "ghost.txt"  # 不存在
    svc = _svc()
    out = svc._add_date("f", {"format": "%Y", "source": "file"}, missing)
    assert out[1:].isdigit()  # 走 except 分支,用 datetime.now()


# ---------------------------------------------------------------------------
# _delete_chars 各分支(suffix / text / 异常)
# ---------------------------------------------------------------------------


def test_delete_chars_suffix():
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "suffix", "value": "2"}) == "abcd"


def test_delete_chars_suffix_zero_returns_name():
    svc = _svc()
    assert svc._delete_chars("abc", {"delete_type": "suffix", "value": "0"}) == "abc"


def test_delete_chars_text():
    svc = _svc()
    assert svc._delete_chars("abcabc", {"delete_type": "text", "value": "b"}) == "acac"


def test_delete_chars_prefix_non_numeric_returns_name():
    svc = _svc()
    assert svc._delete_chars("abc", {"delete_type": "prefix", "value": "x"}) == "abc"


def test_delete_chars_unknown_type_returns_name():
    svc = _svc()
    assert svc._delete_chars("abc", {"delete_type": "weird"}) == "abc"


# ---------------------------------------------------------------------------
# apply_operations 异常分支 & execute_rename 边界
# ---------------------------------------------------------------------------


def test_apply_operations_handles_exception(monkeypatch, tmp_path):
    """让 _apply_single_operation 抛异常 → 走 except,记录错误状态。"""
    f = tmp_path / "a.txt"
    f.write_text("x")
    svc = _svc()

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "_apply_single_operation", boom)
    result = svc.apply_operations([f], [{"type": "add_prefix", "params": {"text": "P_"}}])
    new_path, status = result[f]
    assert new_path == f
    assert "错误" in status


def test_execute_rename_skips_identical_path(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    svc = _svc()
    count, errors = svc.execute_rename({f: f})
    assert count == 0
    assert not errors


def test_execute_rename_target_exists_error(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    existing = tmp_path / "b.txt"
    existing.write_text("y")
    svc = _svc()
    count, errors = svc.execute_rename({src: existing})
    assert count == 0
    assert any("已存在" in e for e in errors)


def test_execute_rename_oserror_captured(tmp_path):
    """模拟 rename 抛普通 Exception → 计入 errors。"""
    src = tmp_path / "a.txt"
    src.write_text("x")
    new = tmp_path / "c.txt"
    svc = _svc()

    orig_rename = Path.rename

    def fail_rename(self, target):
        raise OSError("disk full")

    try:
        Path.rename = fail_rename  # type: ignore[method-assign]
        count, errors = svc.execute_rename({src: new})
    finally:
        Path.rename = orig_rename  # type: ignore[method-assign]
    assert count == 0
    assert errors


def test_get_file_info_delegates(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    info = _svc().get_file_info(f)
    assert info["is_file"] is True
    assert info["size"] == 5


# ---------------------------------------------------------------------------
# _add_date:source=file 文件存在但 stat 抛异常(行 271-272)
# ---------------------------------------------------------------------------


def test_add_date_file_source_stat_exception_falls_back_to_now(tmp_path, monkeypatch):
    """文件存在但 stat() 抛异常 → except → 用 datetime.now()(行 271-272)。"""
    f = tmp_path / "x.txt"
    f.write_text("y")
    monkeypatch.setattr(
        Path,
        "stat",
        # 真实 Path.stat 接受 *, follow_symlinks 等关键字参数(Python 3.12+ exists() 会传
        # follow_symlinks)。用 **kwargs 兼容,避免 pytest 内部 cleanup 调 .exists() 时
        # 因签名不符 INTERNALERROR。
        lambda self, **kw: (_ for _ in ()).throw(PermissionError("stat boom")),
    )
    out = _svc()._add_date("f", {"format": "%Y", "source": "file"}, f)
    # 走 except,用 now() 的年份(4 位数字)
    assert out.startswith("f")
    assert out[1:].isdigit()


# ---------------------------------------------------------------------------
# _delete_chars:suffix value 非数字(行 299-300)
# ---------------------------------------------------------------------------


def test_delete_chars_suffix_non_numeric_returns_name():
    """suffix value 非数字 → ValueError → 返回原名(行 299-300)。"""
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "suffix", "value": "abc"}) == "abcdef"


def test_delete_chars_prefix_non_numeric_value_returns_original():
    """prefix value 非数字 → ValueError → 返回原名(行 291-292 已覆盖,补确认)。"""
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "prefix", "value": "xyz"}) == "abcdef"


# ---------------------------------------------------------------------------
# _delete_chars:prefix value 负数 / 超长(语义反转/清空,B2 回归)
# ---------------------------------------------------------------------------


def test_delete_chars_prefix_negative_value_returns_name():
    """prefix value 为负数 → 应视为无效返回原名,而非反向取尾部。

    回归:旧实现 name[count:] 对 count=-2 取到尾部("ABCDE"→"DE"),语义反转。
    负数对「删除前 N 个字符」无意义,应与非法值同等处理。
    """
    svc = _svc()
    assert svc._delete_chars("ABCDE", {"delete_type": "prefix", "value": "-2"}) == "ABCDE"


def test_delete_chars_suffix_negative_value_returns_name():
    """suffix value 为负数 → 同样应返回原名(与 prefix 一致)。"""
    svc = _svc()
    assert svc._delete_chars("abcdef", {"delete_type": "suffix", "value": "-3"}) == "abcdef"


# ---------------------------------------------------------------------------
# add_number:digits 溢出(序号超过定宽,zfill 不截断)——锁定当前行为
# ---------------------------------------------------------------------------


def test_add_number_digits_overflow_breaks_fixed_width():
    """start=998 digits=3,第 3 个文件序号=1000 超过 3 位,zfill 不截断 → [1000](4 位)。

    锁定当前行为:zfill 只补不截,故溢出产生非定宽标签(破坏字典序/可能撞名)。
    未来若新增「溢出报错」逻辑,该测试应变红提醒有意更新。
    """
    svc = _svc()
    # index 2 → number = 998 + 2 = 1000
    assert svc._add_number("f", {"start": 998, "digits": 3}, 2) == "f[1000]"


# ---------------------------------------------------------------------------
# apply_operations:多点扩展名 stem 切分 + 空输入(锁定 Path.stem 行为)
# ---------------------------------------------------------------------------


def test_apply_prefix_on_multidot_extension(tmp_path):
    """archive.tar.gz:Path.stem 切分为 "archive.tar"(非 "archive"),操作只作用于 stem。

    锁定 Path 语义:多点扩展名只把最后一段当 suffix,前缀加在 "archive.tar" 前。
    """
    f = tmp_path / "archive.tar.gz"
    f.write_text("x")
    result = _svc().apply_operations([f], [{"type": "add_prefix", "params": {"text": "P_"}}])
    assert result[f][0].name == "P_archive.tar.gz"


def test_apply_operations_empty_files_returns_empty(tmp_path):
    """空文件列表 → 返回空 dict(边界)。"""
    assert _svc().apply_operations([], [{"type": "add_prefix", "params": {"text": "P_"}}]) == {}


def test_apply_operations_empty_operations_marks_ready_unchanged(tmp_path):
    """空操作列表 → 文件名不变,标记就绪(new_path == 原路径)。锁定当前行为。"""
    f = tmp_path / "a.txt"
    f.write_text("x")
    result = _svc().apply_operations([f], [])
    new_path, status = result[f]
    assert new_path == f
    assert "准备" in status


# ---------------------------------------------------------------------------
# execute_rename:PermissionError(行 337)
# ---------------------------------------------------------------------------


def test_execute_rename_permission_error_recorded(tmp_path, monkeypatch):
    """rename 抛 PermissionError → 记入 errors '权限不足'(行 336-337)。"""
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "b.txt"
    monkeypatch.setattr(
        Path, "rename", lambda self, other: (_ for _ in ()).throw(PermissionError("denied"))
    )
    success, errors = _svc().execute_rename({src: dst})
    assert success == 0
    assert any("权限不足" in e for e in errors)


def test_add_number_negative_start_produces_bracketed_negative():
    """负 start 直接产出方括号负数序号(锁定当前行为,数据完整性隐患)。

    _validate_add_number 只校验 digits>=1,完全不校验 start。apply 层 _add_number
    直接 str(start + index).zfill(digits):负数穿过 zfill 产出 'f[-05]' 这类含方括号
    负数的文件名(Windows 合法但语义荒谬,破坏字典序)。锁定当前行为,若未来在
    校验层拦截负 start,此测试应变红提醒。
    """
    svc = _svc()
    assert svc._add_number("f", {"start": -5, "digits": 3}, 0) == "f[-05]"


def test_add_number_negative_start_zero_collision():
    """start=-1 + index=1 → number=0 → '000',与正常 start=0 撞名(锁定当前行为)。

    负 start 的隐藏风险:start=-1、index=1 时 start+index=0,zfill(3) 产出 '000',
    与 start=0、index=0 的产出完全相同 —— 两个独立配置可能产生同序号标签。
    锁定此撞名行为,提醒负 start 的副作用。
    """
    svc = _svc()
    assert svc._add_number("f", {"start": -1, "digits": 3}, 1) == "f[000]"
    # 与正常 start=0 idx=0 撞名
    assert svc._add_number("f", {"start": 0, "digits": 3}, 0) == "f[000]"
