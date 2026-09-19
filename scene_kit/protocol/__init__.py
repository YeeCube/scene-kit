"""RECS 风格的 Scene Kit SoA 前后端协议。"""

from scene_kit.protocol.delta import diff_snapshots
from scene_kit.protocol.snapshot import build_snapshot, export_snapshot
from scene_kit.protocol.types import (
    DELTA_PROTOCOL_NAME,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    CommandResult,
    EntityBatch,
    RelationBatch,
    SnapshotProjection,
    WorldCommand,
    WorldDelta,
    WorldSnapshot,
)
from scene_kit.protocol.validation import (
    ProtocolValidationError,
    validate_delta,
    validate_snapshot,
)

__all__ = [
    "DELTA_PROTOCOL_NAME",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "CommandResult",
    "EntityBatch",
    "ProtocolValidationError",
    "RelationBatch",
    "SnapshotProjection",
    "WorldCommand",
    "WorldDelta",
    "WorldSnapshot",
    "build_snapshot",
    "diff_snapshots",
    "export_snapshot",
    "validate_delta",
    "validate_snapshot",
]
