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
    "SourceLayout",
    "TargetLayout",
    "default_rules",
]
