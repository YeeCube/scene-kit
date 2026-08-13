"""EntityKind —— Agent 类型描述符 v0.2.0。

EntityKind 是用户声明 Agent 类型的入口。它本身不持有任何实体数据，
只描述"这种 Agent 包含哪些属性列"。在 register_kind() 时，
EntityKind 被展开为 RECS EntityPool 的 attr_dtypes 字典。

每个 EntityKind 最终对应一个独立的 RECS EntityPool 实例。

v0.2.0 重构：从布尔开关模式升级为 geometry + tags + parent + dim + type + perceive。

Examples:
    >>> prey = EntityKind("prey", geometry="point",
    ...                   tags={"energy": np.float32, "speed": np.float32})
    >>> dtypes = _kind_to_dtypes(prey)
    >>> print(dtypes.keys())  # _kind, _active, _step_fn, _parent_id, _type, ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# geometry → 位置列 映射表
# ---------------------------------------------------------------------------
_GEOMETRY_POSITION_COLS: dict[str, list[tuple[str, type]]] = {
    "point": [("u", np.float32), ("v", np.float32)],
    "segment": [("t", np.float32)],
    "path": [("t", np.float32)],
    "surface": [("u", np.float32), ("v", np.float32)],
    "volume": [("u", np.float32), ("v", np.float32), ("w", np.float32)],
    "hypergraph": [("vertex_id", np.int64)],
}

# geometry → 自身内在维度 (dim) 默认值
_GEOMETRY_DEFAULT_DIMS: dict[str, float] = {
    "point": 0.0,
    "segment": 1.0,
    "path": 1.0,
    "surface": 2.0,
    "volume": 3.0,
    "hypergraph": -1.0,  # 离散，无连续维度
}


@dataclass
class EntityKind:
    """Agent 类型描述符 v0.2.0。

    声明该类型的 Agent 包含哪些属性列。在 register_kind() 时，
    EntityKind 被展开为 RECS EntityPool 的 attr_dtypes 字典。

    Attributes:
        name: 类型名（如 "prey"、"predator"）。
        geometry: 几何形态。六选一："point"/"segment"/"path"/"surface"/"volume"/"hypergraph"。
        dim: 自身内在维度。float 兼容分形 Hausdorff 维度（远期）。0 = 自动推断。
        parent: 父 kind 名称（字符串），None 表示挂载到 root entity。
        tags: 领域属性字典，展开为 EntityPool 列。{"energy": np.float32, "team": np.int32}。
        type: 分类标签 "AGENT"/"ENTITY"/"OBJECT"/"ENV"（调度优先级 + 渲染分组提示）。
        perceive: 可选感知声明 dict。None 表示不使用感知框架。
    """

    name: str

    # ── 几何形态 (v0.2.0 核心字段) ──
    geometry: str = "point"
    dim: float = 0.0  # 0 = 自动推断
    parent: str | None = None

    # ── 领域属性 (替代旧 custom) ──
    tags: dict[str, Any] = field(default_factory=dict)

    # ── 分类 ──
    type: str = "AGENT"

    # ── 感知声明 (阶段5激活) ──
    perceive: dict | None = None

    def __post_init__(self) -> None:
        if self.geometry not in _GEOMETRY_POSITION_COLS:
            raise ValueError(
                f"geometry 必须是 {list(_GEOMETRY_POSITION_COLS.keys())} 之一，"
                f"当前值: {self.geometry!r}"
            )
        if self.dim == 0.0:
            self.dim = _GEOMETRY_DEFAULT_DIMS[self.geometry]
        valid_types = {"AGENT", "ENTITY", "OBJECT", "ENV"}
        if self.type not in valid_types:
            raise ValueError(f"type 必须是 {valid_types} 之一，当前值: {self.type!r}")


def _kind_to_dtypes(kind: EntityKind) -> dict[str, Any]:
    """将 EntityKind 展开为 RECS EntityPool 可消费的 dtype 字典。

    系统保留列（所有 kind 自动包含）：
    - _kind: U32, _active: bool, _step_fn: int32
    - _parent_id: int64, _type: U16, _state: int32, _state_timer: int32
    无条件预设列：mass (float32), r/g/b/a (uint8), label (U32)
    geometry 决定位置列，tags 展开为列。
    """
    dtypes: dict[str, Any] = {}

    # 系统保留列
    dtypes["_kind"] = "U32"
    dtypes["_active"] = np.bool_
    dtypes["_step_fn"] = np.int32
    dtypes["_parent_id"] = np.int64
    dtypes["_type"] = "U16"
    dtypes["_state"] = np.int32
    dtypes["_state_timer"] = np.int32

    # 无条件预设列
    dtypes["mass"] = np.float32
    dtypes["r"] = np.uint8
    dtypes["g"] = np.uint8
    dtypes["b"] = np.uint8
    dtypes["a"] = np.uint8
    dtypes["label"] = "U32"

    # geometry → 位置列
    for col_name, dtype in _GEOMETRY_POSITION_COLS[kind.geometry]:
        dtypes[col_name] = dtype

    # tags → 列
    dtypes.update(kind.tags)

    return dtypes
