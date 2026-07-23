"""file_toolbox.core.rename_template 服务的单元测试。

覆盖模板的延迟加载、增删改查、重命名、清空、导入导出等全部公开行为。
所有持久化文件均落到 tmp_path 隔离目录,不污染运行环境。
"""

import json
import time

import pytest

from file_toolbox.core.rename_template import RenameTemplateService


@pytest.fixture
def svc(tmp_path) -> RenameTemplateService:
    """每个用例独立的模板服务,配置文件落到临时目录。"""
    return RenameTemplateService(config_path=tmp_path / "templates.json")


def _ops(tag: str = "x") -> list[dict]:
    """构造一个最小合法操作列表。"""
    return [{"type": "replace", "find": tag, "replace": "y"}]


# --- 加载逻辑 ---


def test_default_config_path_uses_data_dir(tmp_path, monkeypatch):
    # 未传 config_path 时,落到 get_data_dir() / rename_templates.json
    import file_toolbox.core.rename_template as mod

    monkeypatch.setattr(mod, "get_data_dir", lambda: tmp_path)
    svc_default = RenameTemplateService()
    assert svc_default.config_path == tmp_path / "rename_templates.json"


def test_load_missing_file_returns_empty(svc):
    # 配置文件不存在时,templates 应回退为空字典
    assert svc.templates == {}


def test_load_bad_json_returns_empty(tmp_path):
    cfg = tmp_path / "templates.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    svc = RenameTemplateService(config_path=cfg)
    # 损坏 JSON 应回退为空字典而非抛出
    assert svc.templates == {}


def test_templates_lazy_loaded_once(svc, tmp_path):
    # _templates 初始为 None,首次访问才加载
    assert svc._templates is None
    _ = svc.templates
    assert svc._templates is not None
    # add_template 写文件后,磁盘应包含刚添加的模板
    assert svc.add_template("t1", _ops()) is True
    on_disk = json.loads((tmp_path / "templates.json").read_text(encoding="utf-8"))
    assert "t1" in on_disk


# --- 增 ---


def test_add_template_success(svc):
    assert svc.add_template("t1", _ops(), description="d") is True
    tpl = svc.get_template("t1")
    assert tpl is not None
    assert tpl["operations"] == _ops()
    assert tpl["description"] == "d"
    assert "created_at" in tpl
    assert "updated_at" in tpl


def test_add_template_empty_name_or_ops_returns_false(svc):
    assert svc.add_template("", _ops()) is False
    assert svc.add_template("t1", []) is False
    assert svc.add_template("", []) is False
    assert svc.template_exists("t1") is False


def test_add_template_duplicate_returns_false(svc):
    assert svc.add_template("t1", _ops()) is True
    assert svc.add_template("t1", _ops("z")) is False
    # 原模板未被覆盖
    assert svc.get_template("t1")["operations"] == _ops()


# --- 改 ---


def test_update_template(svc):
    svc.add_template("t1", _ops())
    assert svc.update_template("t1", _ops("z"), description="upd") is True
    tpl = svc.get_template("t1")
    assert tpl["operations"] == _ops("z")
    assert tpl["description"] == "upd"


def test_update_nonexistent_returns_false(svc):
    assert svc.update_template("nope", _ops()) is False


# --- 删 ---


def test_delete_template(svc):
    svc.add_template("t1", _ops())
    assert svc.delete_template("t1") is True
    assert svc.template_exists("t1") is False


def test_delete_nonexistent_returns_false(svc):
    assert svc.delete_template("nope") is False


# --- 查 ---


def test_get_all_templates_sorted_by_updated_at(svc):
    assert svc.add_template("a", _ops()) is True
    # 让 b 的 updated_at 严格晚于 a(同进程内 isoformat 可能同毫秒)
    time.sleep(0.01)
    assert svc.add_template("b", _ops()) is True
    # 更新 a,使其 updated_at 晚于 b,从而 a 在倒序中排第一
    time.sleep(0.01)
    assert svc.update_template("a", _ops("z")) is True

    result = svc.get_all_templates()
    assert [r["name"] for r in result] == ["a", "b"]
    # 每条记录字段齐全
    for r in result:
        assert {"name", "operations", "description", "created_at", "updated_at"} <= r.keys()


def test_template_exists(svc):
    assert svc.template_exists("t1") is False
    svc.add_template("t1", _ops())
    assert svc.template_exists("t1") is True


# --- 重命名 ---


def test_rename_template(svc):
    svc.add_template("t1", _ops())
    assert svc.rename_template("t1", "t2") is True
    assert svc.template_exists("t1") is False
    assert svc.template_exists("t2") is True


def test_rename_nonexistent_or_collision_returns_false(svc):
    # 源不存在
    assert svc.rename_template("nope", "t2") is False
    # 目标已存在(冲突)
    svc.add_template("t1", _ops())
    svc.add_template("t2", _ops())
    assert svc.rename_template("t1", "t2") is False
    # 冲突时源仍存在
    assert svc.template_exists("t1") is True


# --- 清空 ---


def test_clear_all(svc):
    svc.add_template("t1", _ops())
    svc.add_template("t2", _ops())
    svc.clear_all()
    assert svc.templates == {}
    assert svc.get_all_templates() == []
    # 清空应持久化到磁盘:新建服务实例仍为空
    svc2 = RenameTemplateService(config_path=svc.config_path)
    assert svc2.templates == {}


# --- 导出 / 导入 ---


def test_export_and_import_template(svc, tmp_path):
    svc.add_template("t1", _ops(), description="d")
    out = tmp_path / "exp.json"
    assert svc.export_template("t1", str(out)) is True
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["template_name"] == "t1"
    assert payload["template_data"]["operations"] == _ops()

    # 导入到新的服务实例(无同名模板)
    svc2 = RenameTemplateService(config_path=tmp_path / "other.json")
    imported = svc2.import_template(str(out))
    assert imported == "t1"
    assert svc2.template_exists("t1")


def test_import_nonexistent_file_returns_none(svc, tmp_path):
    assert svc.import_template(str(tmp_path / "missing.json")) is None


def test_import_name_collision_adds_suffix(svc, tmp_path):
    svc.add_template("t1", _ops())
    out = tmp_path / "exp.json"
    assert svc.export_template("t1", str(out)) is True
    # 导入到已存在 t1 的服务,应自动加后缀 _1
    imported = svc.import_template(str(out))
    assert imported == "t1_1"
    assert svc.template_exists("t1")
    assert svc.template_exists("t1_1")


def test_export_nonexistent_returns_false(svc, tmp_path):
    assert svc.export_template("nope", str(tmp_path / "out.json")) is False


def test_export_oserror_returns_false(svc, tmp_path):
    # 导出目标路径不可写(用已存在目录)触发 OSError -> 返回 False
    svc.add_template("t1", _ops())
    assert svc.export_template("t1", str(tmp_path)) is False


def test_import_invalid_payload_returns_none(svc, tmp_path):
    # 导入文件缺少 template_name / template_data 时返回 None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"template_name": "x"}), encoding="utf-8")
    assert svc.import_template(str(bad)) is None


def test_import_bad_json_returns_none(svc, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert svc.import_template(str(bad)) is None
