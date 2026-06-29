"""updater 替换层测试。"""

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
