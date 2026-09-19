"""Scene Kit 前后端协议的公共类型与 projection 配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, TypeAlias

PROTOCOL_NAME = "scene-kit.world-snapshot"
DELTA_PROTOCOL_NAME = "scene-kit.world-delta"
PROTOCOL_VERSION = "1.1"

WorldSnapshot: TypeAlias = dict[str, Any]
WorldDelta: TypeAlias = dict[str, Any]
EntityBatch: TypeAlias = dict[str, Any]
RelationBatch: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class SnapshotProjection:
    """声明快照需要导出的 kind、列和空间范围。

    ``columns`` 可以是所有 kind 共用的列序列，也可以是 kind 到列序列的映射。
    ``uid`` 会始终导出，并且不需要显式写入 columns。
    """

    kinds: tuple[str, ...] | None = None
    columns: Mapping[str, Sequence[str]] | Sequence[str] | None = None
    viewport: Mapping[str, float] | None = None
    include_relations: bool = True
    include_metrics: bool = True
    include_world_coordinates: bool = False

    @classmethod
    def from_value(
        cls, value: "SnapshotProjection | Mapping[str, Any] | None"
    ) -> "SnapshotProjection":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        kinds_value = value.get("kinds")
        kinds = tuple(str(item) for item in kinds_value) if kinds_value is not None else None
        return cls(
            kinds=kinds,
            columns=value.get("columns"),
            viewport=value.get("viewport"),
            include_relations=bool(value.get("include_relations", True)),
            include_metrics=bool(value.get("include_metrics", True)),
            include_world_coordinates=bool(value.get("include_world_coordinates", False)),
        )

    def columns_for(self, kind: str, defaults: Sequence[str]) -> tuple[str, ...]:
        if self.columns is None:
            return tuple(defaults)
        if isinstance(self.columns, Mapping):
            selected = self.columns.get(kind, defaults)
        else:
            selected = self.columns
        return tuple(dict.fromkeys(str(name) for name in selected))


@dataclass(frozen=True)
class WorldCommand:
    """可序列化的模型控制或状态修改命令。"""

    type: str
    command_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    """命令执行结果。"""

    command_id: str
    accepted: bool
    applied_tick: int
    error: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "commandId": self.command_id,
            "accepted": self.accepted,
            "appliedTick": self.applied_tick,
            "error": self.error,
            "data": dict(self.data),
        }
