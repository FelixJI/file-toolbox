"""替换层:整目录替换 + 重启。

策略:
  主程序退出前:解压新 zip 到旁路目录 → 生成 .bat helper → startfile 启动 → 退出
  .bat helper(主程序已退出):
    PID 轮询等旧 exe 退出 → .old 回滚式整目录替换 → 重启 → 自删

不下载(那是 downloader),不碰网络。.bat 真跑属集成测试,本模块只验证生成逻辑。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from file_toolbox.updater.errors import ReplaceError

# 重启的目标 exe 名(便携包产物)
_EXE_NAME = "FileToolbox.exe"
# 旧目录备份名(rename 后的临时名,与 OLD_DIR 同级)
_OLD_BACKUP_NAME = "FileToolbox.old"
# PID 等待轮询上限(每 200ms 一次,约 30s)
_WAIT_TRIES = 150


def build_bat_content(old_dir: str, new_dir: str, pid: int) -> str:
    """生成替换+重启的 .bat 内容。

    old_dir: 当前 FileToolbox 目录绝对路径(被替换方)
    new_dir: FileToolbox.new 旁路目录(新内容)
    pid:     当前主进程 PID(helper 等它退出)

    流程:
      1. 循环 tasklist 等 PID 消失(每 200ms,最多 ~30s 后放弃留日志)
      2. rename old → FileToolbox.old(可回滚点)
      3. move new → old 原位置(就位)
      4. move 成功 → 清理 .old + 重启 + 自删
      5. move 失败 → rename .old 回滚 → 写日志退出(不静默消失)

    注:.old 与 OLD_DIR 同级(都在其父目录下),故回滚/清理用 OLD_DIR 父目录,
        而非 %~dp0(helper 自身所在 %TEMP%)。
    """
    parent = Path(old_dir).parent
    old_dir_name = Path(old_dir).name
    log = f"%TEMP%\\ftb_update_{pid}.log"
    # set "VAR=value" 语法:引号包裹整个赋值,含空格/特殊字符的路径被正确保护,
    # 引用时统一用 "%VAR%"(变量值本身不带引号,避免双引号嵌套)。
    return f"""@echo off
:: File Toolbox 自更新 helper(运行时生成,非仓库产物)
set "OLD_DIR={old_dir}"
set "NEW_DIR={new_dir}"
set "OLD_PID={pid}"
set "LOG={log}"
echo [%date% %time%] update start > "%LOG%"

:: 1. 循环等待旧 exe 退出(每 200ms,最多 {_WAIT_TRIES} 次约 30s)
::    注意:下方 if 用单行形式(非多行块),每轮循环重新解析 %TRIES%,
::    故无需 setlocal enabledelayedexpansion。切勿改成多行 if 块。
set TRIES=0
:wait
tasklist /FI "PID eq %OLD_PID%" 2>nul | find "%OLD_PID%" >nul
if errorlevel 1 goto done_wait
set /a TRIES+=1
if %TRIES% GEQ {_WAIT_TRIES} (
    echo [%time%] timeout waiting PID %OLD_PID% >> "%LOG%"
    goto done_wait
)
ping 127.0.0.1 -n 1 -w 200 >nul
goto wait
:done_wait
echo [%time%] old exe exited >> "%LOG%"

:: 2. rename 旧目录为 {_OLD_BACKUP_NAME}(可回滚点;新名与 OLD_DIR 同级)
rename "%OLD_DIR%" {_OLD_BACKUP_NAME}
if errorlevel 1 (
    echo [%time%] rename old failed >> "%LOG%"
    goto fail_no_rollback
)

:: 3. move 新目录就位
move /Y "%NEW_DIR%" "%OLD_DIR%"
if errorlevel 1 (
    echo [%time%] move failed, rollback rename {_OLD_BACKUP_NAME} -> {old_dir_name} >> "%LOG%"
    rename "{parent}\\{_OLD_BACKUP_NAME}" {old_dir_name}
    goto fail_no_rollback
)

:: 4. 清理 .old + 重启 + 自删
rd /s /q "{parent}\\{_OLD_BACKUP_NAME}" 2>nul
echo [%time%] replaced, restarting >> "%LOG%"
start "" "%OLD_DIR%\\{_EXE_NAME}"
(goto) 2>nul & del "%~f0"

:fail_no_rollback
echo [%time%] update FAILED, manual intervention needed >> "%LOG%"
:: 失败弹窗提示用户(模态,点击后继续),日志已留 %TEMP% 供排错,随后 helper 自删
mshta "javascript:var s=new ActiveXObject('WScript.Shell');s.Popup('更新失败,请查看 %TEMP%\\ftb_update_{pid}.log',0,'File Toolbox 更新',16);close()"
(goto) 2>nul & del "%~f0"
"""


# 模块级别名,便于测试 monkeypatch。os.startfile 仅 Windows 存在;在模块级直接取属性会
# 让本模块在 Linux(CI 的 pytest 收集阶段)import 即抛 AttributeError。故用 getattr 回退:
# Windows 上拿到真 os.startfile;其他平台为 None(自更新本就是 Windows 专属功能,非 Windows
# 调到 replace_dir 会因 _startfile 为 None 而显式失败,而非 import 时崩溃)。
_startfile: Callable[[str], None] | None = getattr(os, "startfile", None)


def _extract_portable_zip(zip_path: Path, dest_dir: Path) -> None:
    """解压便携 zip 到 dest_dir。

    build_exe 产物结构:FileToolbox-{ver}-win64.zip 内顶层为 FileToolbox/ 目录。
    本函数把 FileToolbox/ 内的内容解压到 dest_dir(即新目录本体)。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            # zip 内路径形如 FileToolbox/xxx(或 FileToolbox/sub/xxx)
            parts = member.split("/")
            if len(parts) < 2 or parts[0] != "FileToolbox":
                continue
            rel = "/".join(parts[1:])
            if not rel:
                continue
            target = dest_dir / rel
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))


def replace_dir(zip_path: Path, exe_path: Path) -> Path:
    """解压新 zip + 生成 .bat helper + 启动 helper。

    主程序调用本函数后应立即退出(QApplication.quit / sys.exit),
    由 helper 完成整目录替换 + 重启。

    zip_path: 校验过的便携 zip(来自 download_and_verify)
    exe_path: 当前运行的 exe 路径(sys.executable)
    返回: 生成的 .bat helper 路径
    """
    old_dir = Path(exe_path).parent
    new_dir = old_dir.parent / "FileToolbox.new"
    # 清理可能残留的旧 .new(上次更新中断遗留)
    if new_dir.exists():
        shutil.rmtree(new_dir, ignore_errors=True)

    _extract_portable_zip(zip_path, new_dir)

    # 防御性校验:解压出的新目录必须含目标 exe,否则中止(绝不把好程序换成空目录)。
    # zip 结构异常(无 FileToolbox/ 顶层 / exe 缺失)会在此暴露,而非静默替换失败。
    if not (new_dir / _EXE_NAME).is_file():
        shutil.rmtree(new_dir, ignore_errors=True)
        raise ReplaceError(
            f"更新包结构异常:未在解压结果中找到 {_EXE_NAME},已中止替换(原程序未受影响)"
        )

    bat_content = build_bat_content(
        old_dir=str(old_dir),
        new_dir=str(new_dir),
        pid=os.getpid(),
    )
    pid = os.getpid()
    bat_path = Path(tempfile.gettempdir()) / f"ftb_update_{pid}.bat"
    bat_path.write_text(bat_content, encoding="utf-8")

    if _startfile is None:  # 非 Windows(os.startfile 不存在)
        raise ReplaceError("自更新仅在 Windows 上可用:缺少 os.startfile")
    _startfile(str(bat_path))
    return bat_path
