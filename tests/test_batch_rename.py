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
