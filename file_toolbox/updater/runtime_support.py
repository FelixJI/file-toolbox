"""更新运行态的本地只读探针(无网络)。

集中封装"从 Velopack SDK 读本机安装事实"的能力,供三处消费:
- GUI 展示运行版本(打包态以安装清单为准,见 ``metadata.runtime_version``);
- 启动时跨启动更新对账(main_window);
- 诊断日志。构造 ``UpdateManager`` 只读本地安装清单,不发网络请求。
"""

from __future__ import annotations

from dataclasses import dataclass

import velopack

from file_toolbox.updater.transport import DEFAULT_FEED


@dataclass(frozen=True)
class UpdateRuntimeState:
    """本机 Velopack 安装布局的快照。"""

    available: bool  # 安装布局有效(UpdateManager 可构造)
    current_version: str  # SDK 本机当前版本;布局无效时为空串
    is_portable: bool
    pending_restart_version: str | None  # 已下载待重启应用的更新版本
    error: str  # 布局无效时的错误摘要(诊断用)


def _new_manager() -> velopack.UpdateManager:
    options = velopack.UpdateOptions(False, -1, "win")
    return velopack.UpdateManager(velopack.HttpSource(DEFAULT_FEED), options)


def probe_update_runtime() -> UpdateRuntimeState:
    """读取本机安装事实;布局无效不抛异常,返回 available=False 的快照。"""

    try:
        manager = _new_manager()
        pending = manager.get_update_pending_restart()
        return UpdateRuntimeState(
            available=True,
            current_version=str(manager.get_current_version()),
            is_portable=bool(manager.get_is_portable()),
            pending_restart_version=str(pending.Version) if pending is not None else None,
            error="",
        )
    except Exception as error:  # noqa: BLE001 — 布局缺失/SDK 异常统一降级为不可用
        return UpdateRuntimeState(False, "", False, None, str(error))


def packaged_version() -> str | None:
    """打包形态下从 Velopack 安装清单读本机当前版本;不可用时 None。

    源码/开发运行(无有效安装布局)与清单读取失败都返回 None,调用方回落
    importlib 元数据;不在 common 层重复实现以保持单一来源。
    """

    state = probe_update_runtime()
    if not state.available:
        return None
    return state.current_version or None
