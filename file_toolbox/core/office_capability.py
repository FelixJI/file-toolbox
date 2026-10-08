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
    kind: str,
    suffixes: tuple[str, ...] = (),
    *,
    engines: tuple[str, ...] = ("office", "wps"),
    refresh: bool = False,
) -> CapabilityStatus:
    """查询单类 Office 应用的可用性(注册表预筛,毫秒级,不启动 Office)。

    engines 是调用工具的适配器实际支持的套件集合(F7):选择在集合内进行
    (引擎管理器内完成,复用同一份预筛 memo/verified 证据)——仅 MS 的工具
    不会继承 PDF 回退 WPS 的 verified 证据,但 MS 预筛命中仍如实展示;
    命中套件不在集合内时接 MISSING,详情说明检测到但该工具不支持。
    """
    label = _KIND_LABELS.get(kind, kind)
    requirement = f"{label}({_format_suffixes(suffixes)})" if suffixes else label
    availability: KindAvailability = EngineManager().kind_availability(
        kind, refresh=refresh, engines=engines
    )
    if availability.state is ProbeState.AVAILABLE:
        engine = _ENGINE_LABELS.get(availability.engine or "", availability.engine or "?")
        if availability.detail:
            # 回退命中但另一套件探测失败(P4):如实保留探测错误,不因命中丢弃
            engine = f"{engine};另一套件探测失败({availability.detail})"
        return CapabilityStatus(
            requirement=requirement,
            state=ProbeState.AVAILABLE,
            detail=engine,
            verified=availability.verified,
        )
    if availability.state is ProbeState.MISSING and availability.engine:
        detected = _ENGINE_LABELS.get(availability.engine, availability.engine)
        supported = "/".join(_ENGINE_LABELS.get(item, item) for item in engines)
        return CapabilityStatus(
            requirement=requirement,
            state=ProbeState.MISSING,
            detail=f"检测到{detected},但该工具仅支持 {supported}",
        )
    return CapabilityStatus(
        requirement=requirement,
        state=availability.state,
        detail=availability.detail,
    )


def record_office_session_success(kind: str, engine: str = "office") -> None:
    """登记一次非 PDF 适配器的真实 Office COM 会话成功(能力层入口)。

    考勤等直接经 common.office_session 建会话的适配器在 Dispatch 成功后调用;
    复用 EngineManager 进程内 kind 证据(单一存储,不建第二份缓存/全局回调
    框架),让页面能力提示与 full 自测前置读到"已验证"。kind/engine 语义
    同 EngineManager.record_kind_success。
    """
    EngineManager.record_kind_success(kind, engine)


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
        office_kind_status(need.kind, need.suffixes, engines=need.engines, refresh=refresh)
        for need in spec.office_needs
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
