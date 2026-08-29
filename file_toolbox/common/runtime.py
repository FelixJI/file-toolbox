"""运行形态判定:区分源码运行与打包发行(Nuitka / PyInstaller)。"""

import sys


def is_packaged_runtime() -> bool:
    """是否运行在打包发行形态(供 Velopack hook、启动自动检查等 gate 使用)。

    - PyInstaller:设置 ``sys.frozen``。
    - Nuitka standalone:**不**设置 ``sys.frozen``,且 ``sys.executable`` 合成为
      dist 内的 ``python.exe``(文件并不存在);可靠信号是编译入口模块的
      ``__compiled__`` 全局。

    0.2.9-0.2.11 的实际故障:各 gate 只看 ``sys.frozen``,Nuitka 便携包被当成
    源码运行——Velopack hook 被跳过,更新器把拉起完整 GUI 的 hook 进程 15s
    超时强杀;启动自动检查更新也从未运行。
    """
    if bool(getattr(sys, "frozen", False)):
        return True
    main = sys.modules.get("__main__")
    return main is not None and hasattr(main, "__compiled__")
