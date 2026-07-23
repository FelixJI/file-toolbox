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
