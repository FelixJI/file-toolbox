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
