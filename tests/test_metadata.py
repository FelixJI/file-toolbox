"""metadata 模块测试:元信息常量与 CHANGELOG 读取。"""

import file_toolbox
from file_toolbox.common import metadata


def test_version_matches_package():
    assert file_toolbox.__version__ == metadata.VERSION


def test_app_name_is_file_toolbox():
    assert metadata.APP_NAME == "File Toolbox"


def test_repo_url_is_https():
    assert metadata.REPO_URL.startswith("https://")


def test_license_is_mit():
    assert metadata.LICENSE == "MIT"


def test_tech_stack_is_list_of_tuples():
    assert isinstance(metadata.TECH_STACK, list)
    assert len(metadata.TECH_STACK) > 0
    for item in metadata.TECH_STACK:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_python_requirement_string():
    assert "3.11" in metadata.PYTHON_REQUIREMENT


def test_get_changelog_finds_repo_root():
    """开发环境:CHANGELOG.md 在仓库根,应返回完整内容。"""
    text = metadata.get_changelog()
    assert isinstance(text, str)
    assert "Changelog" in text or "changelog" in text.lower()


def test_get_changelog_fallback_when_missing(tmp_path, monkeypatch):
    """模拟找不到 CHANGELOG.md:切到空目录,断言返回兜底字符串(含版本号),不抛异常。"""
    monkeypatch.chdir(tmp_path)
    # 同时屏蔽仓库根查找:让 _repo_root_changelog_path 指向不存在的地方
    monkeypatch.setattr(
        metadata, "_repo_root_changelog_path", lambda: tmp_path / "nope.md"
    )
    text = metadata.get_changelog()
    assert isinstance(text, str)
    assert file_toolbox.__version__ in text  # 兜底文本含版本号


def test_get_changelog_finds_portable_exe_sibling(tmp_path, monkeypatch):
    """模拟便携 exe 形态:sys.executable 同级目录(Nuitka .dist 根)有 CHANGELOG.md,
    仓库根查找屏蔽、cwd 为空 → 应从 exe 同级读到(随包分发的 CHANGELOG)。

    覆盖 metadata.get_changelog 回退链第 2 级(便携 exe 同级)。
    """
    # 模拟 exe 在 tmp_path/bin/FileToolbox.exe,CHANGELOG 放在 exe 同级(bin/)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_exe = bin_dir / "FileToolbox.exe"
    fake_exe.write_text("not-a-real-exe")
    changelog = bin_dir / "CHANGELOG.md"
    changelog.write_text("# Portable changelog content", encoding="utf-8")

    monkeypatch.setattr(metadata.sys, "executable", str(fake_exe))
    # 屏蔽仓库根查找(开发环境回退),强制走 exe 同级
    monkeypatch.setattr(metadata.sys, "platform", "win32")
    monkeypatch.setattr(
        metadata, "_repo_root_changelog_path", lambda: tmp_path / "nope.md"
    )
    # cwd 指向空目录,避免误命中
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)

    text = metadata.get_changelog()
    assert text == "# Portable changelog content"
