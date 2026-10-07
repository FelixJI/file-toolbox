"""按操作/文件类型的外部能力状态查询(消费统一工具登记声明)。

纯查询模块,职责边界:
- 不导入 Qt/不启动 Office 进程/不发网络请求;Office 状态复用 EngineManager
  的注册表预筛、进程内 memo 与真实 Dispatch 证据(不新造缓存系统);
- Pandoc 状态复用 MarkdownConvertService 的包内定位(无 PATH/联网回退,
  仅用于 docx 目标);
- 查询结果只用于页面提示与自测判定,不据此禁用页面/按钮——依赖缺失只影响
  对应操作,纯文件路径不受无关引擎影响,失败在执行期如实报错。

语义约定:注册表命中只是"检测到"预筛结论,不冒称真实 COM 可用;只有本进程
真实 Dispatch 成功(verified)才展示"已验证"。三态直接复用 engine_manager
的 ProbeState,不另设映射层。
"""

from __future__ import annotations

from dataclasses import dataclass

from file_toolbox.common.tool_registry import spec_by_tool_id
from file_toolbox.core.batch_pdf.engine_manager import (
    EngineManager,
    KindAvailability,
    ProbeState,
)
from file_toolbox.core.markdown_convert import locate_bundled_pandoc

# kind -> 展示名(与 EngineManager._APP_CONFIG 的三类应用一致)
_KIND_LABELS = {"word": "Word", "excel": "Excel", "ppt": "PowerPoint"}
_ENGINE_LABELS = {"office": "MS Office", "wps": "WPS"}
_PANDOC_TARGET = ".docx"  # Markdown 的 Pandoc 仅用于 docx 目标(xlsx 为纯库转换)


@dataclass(frozen=True)
class CapabilityStatus:
    """单条能力需求的状态(供页面提示与自测判定展示)。"""

    requirement: str  # 展示名,如 "Word(doc/docx)"、"内置 Pandoc(docx)"
    state: ProbeState
    detail: str = ""  # 引擎名/资源路径/错误原因
    verified: bool = False  # 仅 Office:本进程真实 Dispatch 成功过


def _format_suffixes(suffixes: tuple[str, ...]) -> str:
    return "/".join(suffix.lstrip(".") for suffix in suffixes) if suffixes else ""


def office_kind_status(
    kind: str, suffixes: tuple[str, ...] = (), *, refresh: bool = False
) -> CapabilityStatus:
    """查询单类 Office 应用的可用性(注册表预筛,毫秒级,不启动 Office)。"""
    label = _KIND_LABELS.get(kind, kind)
    requirement = f"{label}({_format_suffixes(suffixes)})" if suffixes else label
    availability: KindAvailability = EngineManager().kind_availability(kind, refresh=refresh)
    if availability.state is ProbeState.AVAILABLE:
        engine = _ENGINE_LABELS.get(availability.engine or "", availability.engine or "?")
        return CapabilityStatus(
            requirement=requirement,
            state=ProbeState.AVAILABLE,
            detail=engine,
            verified=availability.verified,
        )
    return CapabilityStatus(
        requirement=requirement,
        state=availability.state,
        detail=availability.detail,
    )


def pandoc_status() -> CapabilityStatus:
    """查询包内 Pandoc 就绪状态(仅 docx 目标;只查包内路径,无 PATH/下载回退)。"""
    requirement = f"内置 Pandoc({_format_suffixes((_PANDOC_TARGET,))})"
    try:
        path = locate_bundled_pandoc()
    except ImportError as error:
        return CapabilityStatus(
            requirement=requirement, state=ProbeState.MISSING, detail=str(error)
        )
    return CapabilityStatus(requirement=requirement, state=ProbeState.AVAILABLE, detail=str(path))


def tool_capability_statuses(tool_id: str, *, refresh: bool = False) -> list[CapabilityStatus]:
    """按统一工具登记声明取该工具的全部外部能力状态。

    纯文件工具(无 office_needs 且不 requires_pandoc)返回空列表:页面可据此
    展示"纯文件处理"且绝不因引擎状态受影响。
    """
    spec = spec_by_tool_id(tool_id)
    if spec is None:
        raise ValueError(f"未登记的工具: {tool_id!r}")
    statuses = [
        office_kind_status(need.kind, need.suffixes, refresh=refresh) for need in spec.office_needs
    ]
    if spec.requires_pandoc:
        statuses.append(pandoc_status())
    return statuses


def format_status(status: CapabilityStatus) -> str:
    """单条状态文案(明确区分预筛命中与真实验证,不冒称 COM 可用)。"""
    if status.state is ProbeState.AVAILABLE:
        if status.verified:
            return f"{status.requirement}: 已验证可用({status.detail})"
        return f"{status.requirement}: 检测到({status.detail})"
    if status.state is ProbeState.PROBE_ERROR:
        return f"{status.requirement}: 检测失败({status.detail})"
    suffix = f"({status.detail})" if status.detail else ""
    return f"{status.requirement}: 未检测到{suffix}"


def format_statuses(statuses: list[CapabilityStatus]) -> str:
    """页面提示文案:多条以「；」连接;含未验证的预筛命中时附预检限定语。"""
    if not statuses:
        return "纯文件处理,无需外部引擎"
    parts = [format_status(status) for status in statuses]
    office_unverified = any(
        status.state is ProbeState.AVAILABLE
        and not status.verified
        and not status.requirement.startswith("内置 Pandoc")
        for status in statuses
    )
    if office_unverified:
        parts.append("预检结论,实际以执行结果为准")
    return "；".join(parts)
