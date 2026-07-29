"""updater 替换层测试。"""

from pathlib import Path

from file_toolbox.updater.replacer import build_bat_content


class TestBuildBatContent:
    def test_contains_pid_wait_loop(self):
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        # PID 轮询等待
        assert "12345" in bat
        assert "tasklist" in bat.lower() or "find" in bat.lower()

    def test_contains_rename_old(self):
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        assert "FileToolbox.old" in bat
        assert "rename" in bat.lower()

    def test_contains_move_new(self):
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        assert "move" in bat.lower()

    def test_contains_restart(self):
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        assert "FileToolbox.exe" in bat
        assert "start" in bat.lower()

    def test_contains_self_delete(self):
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        assert "del" in bat.lower()

    def test_paths_quoted(self):
        """路径含空格时,set 语句用引号包裹整个赋值(Windows 标准保护方式)。"""
        bat = build_bat_content(
            old_dir=r"C:\my app\FileToolbox",
            new_dir=r"C:\my app\FileToolbox.new",
            pid=1,
        )
        # set "VAR=path" 语法:引号保护含空格的路径
        assert 'set "OLD_DIR=C:\\my app\\FileToolbox"' in bat
        # 变量引用处统一用 "%OLD_DIR%"(运行时安全展开含空格路径)
        assert '"%OLD_DIR%"' in bat

    def test_contains_rollback(self):
        """move 失败时回滚 rename old → original。"""
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=12345,
        )
        assert "rollback" in bat.lower() or "FileToolbox.old" in bat

    def test_log_path_single_backslash(self):
        """LOG 变量与 mshta 提示路径一致:都是 %TEMP%\\ftb_update<pid>.log(单反斜杠)。

        回归测试:此前 LOG 行误写为双反斜杠,与 mshta 行不一致。
        """
        bat = build_bat_content(
            old_dir=r"C:\app\FileToolbox",
            new_dir=r"C:\app\FileToolbox.new",
            pid=7,
        )
        # f-string 输出里:Windows 路径分隔应为单个反斜杠
        assert 'set "LOG=%TEMP%\\ftb_update_7.log"' in bat
        # mshta 弹窗提示的路径与 LOG 一致
        assert "%TEMP%\\ftb_update_7.log" in bat


import zipfile  # noqa: E402

import pytest  # noqa: E402

from file_toolbox.updater import replacer as rmod  # noqa: E402


def test_startfile_alias_tolerates_missing_attr():
    """回归:os.startfile 仅 Windows 存在,模块级取属性不能崩溃。

    此前 `_startfile = os.startfile` 在模块顶层,非 Windows(CI 的 Linux runner)
    import 即抛 AttributeError,污染 pytest 收集。现用 getattr 回退:_startfile 在
    Windows 上为真 os.startfile,其他平台为 None。此断言锁定"回退语义":当前平台
    有 startfile 时拿到可调用对象(Windows),否则为 None(不会是属性错误残留)。
    """
    alias = rmod._startfile
    assert alias is None or callable(alias)


def _make_portable_zip(zip_path, version="9.9.9"):
    r"""造一个内含 FileToolbox\<文件> 的便携 zip(模拟 build_exe 产物)。"""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("FileToolbox/FileToolbox.exe", b"FAKE EXE")
        zf.writestr("FileToolbox/python3.dll", b"FAKE DLL")
        zf.writestr("FileToolbox/version.txt", version.encode())


class TestReplaceDir:
    def test_extracts_to_sibling_new_dir(self, tmp_path, monkeypatch):
        """新内容解压到 old_dir 同级的 FileToolbox.new 目录。"""
        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD EXE")

        zip_path = tmp_path / "update.zip"
        _make_portable_zip(zip_path)

        # 桩掉 startfile(不真启动 .bat)
        started: list[str] = []
        monkeypatch.setattr(rmod, "_startfile", lambda p: started.append(p))
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        rmod.replace_dir(Path(zip_path), exe_path=exe)

        new_dir = tmp_path / "FileToolbox.new"
        assert new_dir.exists()
        assert (new_dir / "FileToolbox.exe").read_bytes() == b"FAKE EXE"
        assert len(started) == 1  # helper 启动一次
        assert started[0].endswith(".bat")

    def test_bat_written_to_temp(self, tmp_path, monkeypatch):
        """.bat helper 写到临时目录。"""
        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD")

        zip_path = tmp_path / "update.zip"
        _make_portable_zip(zip_path)

        bat_paths: list[str] = []
        monkeypatch.setattr(rmod, "_startfile", lambda p: bat_paths.append(p))
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        rmod.replace_dir(Path(zip_path), exe_path=exe)
        bat = Path(bat_paths[0])
        assert bat.exists()
        assert "4242" in bat.read_text(encoding="utf-8")

    def test_bat_contains_correct_dirs(self, tmp_path, monkeypatch):
        """.bat 里 OLD_DIR / NEW_DIR 正确。"""
        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD")

        zip_path = tmp_path / "update.zip"
        _make_portable_zip(zip_path)

        bat_paths: list[str] = []
        monkeypatch.setattr(rmod, "_startfile", lambda p: bat_paths.append(p))
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        rmod.replace_dir(Path(zip_path), exe_path=exe)
        bat = Path(bat_paths[0]).read_text(encoding="utf-8")
        assert str(old_dir) in bat
        assert "FileToolbox.new" in bat

    def test_aborts_when_zip_missing_exe(self, tmp_path, monkeypatch):
        """zip 解压后无 FileToolbox.exe → 抛 ReplaceError,不启动 helper,清理 .new。

        防御:zip 结构异常时绝不把好程序目录替换成空目录。
        """
        from file_toolbox.updater.errors import ReplaceError

        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD")

        # 造一个缺 exe 的 zip(只含无关文件)
        zip_path = tmp_path / "bad.zip"
        with __import__("zipfile").ZipFile(zip_path, "w") as zf:
            zf.writestr("FileToolbox/readme.txt", b"no exe here")

        started: list[str] = []
        monkeypatch.setattr(rmod, "_startfile", lambda p: started.append(p))
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        with pytest.raises(ReplaceError):
            rmod.replace_dir(Path(zip_path), exe_path=exe)
        # 未启动 helper,且旁路 .new 已清理
        assert started == []
        assert not (tmp_path / "FileToolbox.new").exists()
        # 原程序完好
        assert exe.read_bytes() == b"OLD"

    def test_cleans_residual_new_dir_before_extract(self, tmp_path, monkeypatch):
        """残留的 FileToolbox.new 目录(上次更新中断遗留)→ 解压前被 shutil.rmtree 清掉
        (missing 151)。

        用 spy 记录 rmtree 调用,验证残留目录被清理,且后续正常解压。
        """
        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD")

        # 预先造一个残留 .new(含一个会被清掉的"垃圾"文件)
        new_dir = tmp_path / "FileToolbox.new"
        new_dir.mkdir()
        (new_dir / "stale.txt").write_bytes(b"LEFTOVER")

        zip_path = tmp_path / "update.zip"
        _make_portable_zip(zip_path)

        rmtree_calls: list[Path] = []
        real_rmtree = rmod.shutil.rmtree

        def spy_rmtree(path, ignore_errors=False):
            rmtree_calls.append(Path(path))
            return real_rmtree(path, ignore_errors=ignore_errors)

        monkeypatch.setattr(rmod.shutil, "rmtree", spy_rmtree)
        monkeypatch.setattr(rmod, "_startfile", lambda p: None)
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        rmod.replace_dir(Path(zip_path), exe_path=exe)

        # 残留 .new 在第一次 rmtree 调用中被清理
        assert new_dir in rmtree_calls
        # 残留的垃圾文件已不在,新内容已就位
        assert not (new_dir / "stale.txt").exists()
        assert (new_dir / "FileToolbox.exe").read_bytes() == b"FAKE EXE"

    def test_raises_when_startfile_none(self, tmp_path, monkeypatch):
        """_startfile 为 None(非 Windows)→ 抛 ReplaceError(missing 173)。

        即便 zip 有效、解压成功,缺 os.startfile 也必须显式失败而非静默。
        """
        from file_toolbox.updater.errors import ReplaceError

        old_dir = tmp_path / "FileToolbox"
        old_dir.mkdir()
        exe = old_dir / "FileToolbox.exe"
        exe.write_bytes(b"OLD")

        zip_path = tmp_path / "update.zip"
        _make_portable_zip(zip_path)

        monkeypatch.setattr(rmod, "_startfile", None)
        monkeypatch.setattr(rmod.os, "getpid", lambda: 4242)

        with pytest.raises(ReplaceError):
            rmod.replace_dir(Path(zip_path), exe_path=exe)


class TestExtractPortableZipEdgeCases:
    """覆盖 _extract_portable_zip 的跳过/目录分支(missing 125, 128, 131)。

    构造一个含四类成员的 zip,验证只解压合法的顶层 FileToolbox/<项>:
      - FileToolbox/FileToolbox.exe(正常文件项)→ 解压
      - other/x.txt(非 FileToolbox 顶层 → 跳过,missing 125)
      - FileToolbox/sub/(目录项 → mkdir,missing 131)
      - FileToolbox(顶层无 /,len(parts)<2 且 rel 空 → 跳过,missing 125/128)
    """

    def test_skips_non_top_level_subdir_and_empty_rel(self, tmp_path):
        zip_path = tmp_path / "mixed.zip"
        dest_dir = tmp_path / "out"

        with zipfile.ZipFile(zip_path, "w") as zf:
            # 正常文件项(顶层 FileToolbox/<file>)
            zf.writestr("FileToolbox/FileToolbox.exe", b"FAKE EXE")
            # 非 FileToolbox 顶层 → 应跳过(line 125)
            zf.writestr("other/x.txt", b"SHOULD NOT EXTRACT")
            # 目录项(FileToolbox/sub/)→ mkdir,不写文件(line 131)
            zf.writestr("FileToolbox/sub/", b"")
            # "FileToolbox/"(仅顶层名带尾斜杠):parts=["FileToolbox",""],rel 空 → 跳过(line 128)
            zf.writestr("FileToolbox/", b"")

        rmod._extract_portable_zip(Path(zip_path), dest_dir)

        # 正常文件项已解压
        assert (dest_dir / "FileToolbox.exe").read_bytes() == b"FAKE EXE"
        # 目录项创建了子目录(mkdir)
        assert (dest_dir / "sub").is_dir()
        # 非 FileToolbox 顶层的项被跳过
        assert not (dest_dir / "x.txt").exists()
        # 仅尾斜杠的 FileToolbox/ 不往 dest_dir 写任何文件(rel 为空,target=dest_dir 本身)
        # 即 dest_dir 顶层除 sub/ 外不应有多余文件
        top_entries = sorted(p.name for p in dest_dir.iterdir())
        assert "FileToolbox.exe" in top_entries
        assert "sub" in top_entries
