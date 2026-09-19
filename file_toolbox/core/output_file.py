"""新输出先完整序列化,再以自动编号的名称排他提交。"""

from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO

from file_toolbox.core.rename_execution import rename_no_replace


def write_numbered_output(output: Path, write: Callable[[IO[bytes]], object]) -> Path:
    """只返回已提交路径;冲突不覆盖,失败只清理本次独占创建的暂存文件。

    暂存文件与目标同目录,避免跨文件系统移动。序列化器只接收已打开的流,
    不会重开候选路径。提交复用平台排他 rename,不支持时明确失败。
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w+b", prefix=".file-toolbox-", dir=output.parent, delete=False
        ) as stream:
            staging = Path(stream.name)
            write(stream.file)
        candidate = output
        counter = 0
        while True:
            try:
                rename_no_replace(staging, candidate)
            except FileExistsError:
                counter += 1
                candidate = output.with_name(f"{output.stem}_{counter}{output.suffix}")
            else:
                return candidate
    except Exception as error:
        try:
            if staging is not None:
                staging.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise OSError(f"{error}; 临时文件清理失败: {staging} ({cleanup_error})") from error
        raise
