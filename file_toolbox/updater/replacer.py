"""替换层:整目录替换 + 重启。

策略:
  主程序退出前:解压新 zip 到旁路目录 → 生成 .bat helper → startfile 启动 → 退出
  .bat helper(主程序已退出):
    PID 轮询等旧 exe 退出 → .old 回滚式整目录替换 → 重启 → 自删

不下载(那是 downloader),不碰网络。.bat 真跑属集成测试,本模块只验证生成逻辑。
"""

from __future__ import annotations

from pathlib import Path

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
    log = f"%TEMP%\\\\ftb_update_{pid}.log"
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
:: 失败弹窗提示(不静默消失),保留 .bat 供排错后自删
mshta "javascript:var s=new ActiveXObject('WScript.Shell');s.Popup('更新失败,请查看 %TEMP%\\ftb_update_{pid}.log',0,'File Toolbox 更新',16);close()"
(goto) 2>nul & del "%~f0"
"""
