"""考勤汇总核心 module。"""

from .plan_store import AttendancePlanStore
from .service import AttendanceCancelled, AttendanceError, AttendanceService
from .types import (
    AttendancePlan,
    AttendancePreview,
    AttendanceRequest,
    AttendanceResult,
    AttendanceRule,
    CellMapping,
    CellRef,
    EmployeeGroupOverride,
    EmployeeGroupPreview,
    GroupSheetConfig,
    RosterConfig,
    RosterLayout,
    SourceLayout,
    TargetLayout,
    UnmatchedAttendance,
    default_rules,
)

__all__ = [
    "AttendanceCancelled",
    "AttendanceError",
    "AttendancePlan",
    "AttendancePlanStore",
    "AttendancePreview",
    "AttendanceRequest",
    "AttendanceResult",
    "AttendanceRule",
    "AttendanceService",
    "UnmatchedAttendance",
    "CellMapping",
    "CellRef",
    "EmployeeGroupOverride",
    "EmployeeGroupPreview",
    "GroupSheetConfig",
    "RosterConfig",
    "RosterLayout",
    "SourceLayout",
    "TargetLayout",
    "default_rules",
]
