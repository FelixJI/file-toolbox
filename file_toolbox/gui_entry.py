"""GUI 独立入口(供 Nuitka 编译为 exe)。

双击 exe 直接启动图形界面;CLI 仍可经 python -m file_toolbox 或 file-toolbox 命令使用。
"""

from file_toolbox.gui.main_window import run_gui

if __name__ == "__main__":
    run_gui()
