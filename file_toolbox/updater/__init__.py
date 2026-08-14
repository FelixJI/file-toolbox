"""File Toolbox 的 Velopack 更新接口。"""

from file_toolbox.updater.coordinator import UpdateCoordinator
from file_toolbox.updater.models import (
    UpdateApplyResult,
    UpdateApplyStatus,
    UpdateCheckResult,
    UpdateCheckStatus,
)
from file_toolbox.updater.proxy import apply_proxy
from file_toolbox.updater.velopack_adapter import (
    VelopackUpdateCoordinator,
    create_update_coordinator,
)

__all__ = [
    "UpdateApplyResult",
    "UpdateApplyStatus",
    "UpdateCheckResult",
    "UpdateCheckStatus",
    "UpdateCoordinator",
    "VelopackUpdateCoordinator",
    "apply_proxy",
    "create_update_coordinator",
]
