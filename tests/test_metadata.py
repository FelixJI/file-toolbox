"""metadata 模块测试:元信息常量与 CHANGELOG 读取。"""

import tomllib
from pathlib import Path

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


def test_python_requirement_matches_pyproject():
    """Python 要求须与 pyproject.toml 的 requires-python 完全一致,防止静默漂移。"""
    repo_root = Path(metadata.__file__).resolve().parents[2]
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == metadata.PYTHON_REQUIREMENT


def test_app_description_covers_all_capabilities():
    """关于页简介必须覆盖 GUI 全部六个功能 Tab,新增功能时同步更新描述。"""
    for keyword in ("重命名", "建文件夹", "PDF", "内容替换", "考勤汇总", "发票识别"):
        assert keyword in metadata.APP_DESCRIPTION


def test_tech_stack_mentions_velopack_updater():
    """应用内更新由 Velopack 提供(README 已声明),技术路线应向用户展示。"""
    names = " ".join(name.lower() for name, _ in metadata.TECH_STACK)
    assert "velopack" in names


def test_get_changelog_finds_repo_root():
    """开发环境:CHANGELOG.md 在仓库根,应返回完整内容。"""
    text = metadata.get_changelog()
    assert isinstance(text, str)
    assert "Changelog" in text or "changelog" in text.lower()


def test_get_changelog_fallback_when_missing(tmp_path, monkeypatch):
    """模拟找不到 CHANGELOG.md:切到空目录,断言返回兜底字符串(含版本号),不抛异常。"""
    monkeypatch.chdir(tmp_path)
    # 同时屏蔽仓库根查找:让 _repo_root_changelog_path 指向不存在的地方
    monkeypatch.setattr(metadata, "_repo_root_changelog_path", lambda: tmp_path / "nope.md")
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
    monkeypatch.setattr(metadata, "_repo_root_changelog_path", lambda: tmp_path / "nope.md")
    # cwd 指向空目录,避免误命中
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)

    text = metadata.get_changelog()
    assert text == "# Portable changelog content"


def test_get_changelog_skips_unreadable_file(tmp_path, monkeypatch):
    """某候选 is_file() 真 but read_text 抛 OSError → continue 到下一候选
    (覆盖 metadata.py 66-67 OSError 分支)。

    让第一候选指向一个"声称是文件但读取抛 OSError"的路径,第二候选 cwd 真实可读
    → get_changelog 应跳过失败候选,返回 cwd 候选内容(不抛 OSError)。
    """
    # cwd 下放真实可读 CHANGELOG.md,作为回退链命中
    real_cwd = tmp_path / "cwd"
    real_cwd.mkdir()
    (real_cwd / "CHANGELOG.md").write_text("# cwd changelog content", encoding="utf-8")
    monkeypatch.chdir(real_cwd)

    # 构造一个"坏"路径对象:is_file() 返回 True,read_text 抛 OSError
    import pathlib

    bad_path = tmp_path / "unreadable.md"
    bad_path.write_text("placeholder", encoding="utf-8")  # 真实存在,便于 mock

    real_is_file = pathlib.Path.is_file
    real_read_text = pathlib.Path.read_text

    def fake_is_file(self):
        if self == bad_path:
            return True
        return real_is_file(self)

    def fake_read_text(self, *args, **kwargs):
        if self == bad_path:
            raise OSError("simulated read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(metadata.Path, "is_file", fake_is_file)
    monkeypatch.setattr(metadata.Path, "read_text", fake_read_text)

    # 让全部 3 个候选都指向 bad_path,确保 OSError 分支被命中
    monkeypatch.setattr(metadata, "_repo_root_changelog_path", lambda: bad_path)
    monkeypatch.setattr(metadata.sys, "executable", str(bad_path))
    # 注意:cwd 候选是真实可读的,但前两候选(is_file=True、read_text 抛 OSError)会 continue
    text = metadata.get_changelog()
    assert text == "# cwd changelog content"
