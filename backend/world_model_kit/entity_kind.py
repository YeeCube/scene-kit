"""EntityKind —— Agent 类型描述符。

EntityKind 是用户声明 Agent 类型的入口。它本身不持有任何实体数据，
只描述"这种 Agent 包含哪些属性列"。在 register_kind() 时，
EntityKind 被展开为 RECS EntityPool 的 attr_dtypes 字典。

每个 EntityKind 最终对应一个独立的 RECS EntityPool 实例。

Examples:
    >>> prey = EntityKind("prey", position=True, velocity=True, energy=True)
    >>> dtypes = _kind_to_dtypes(prey)
    >>> print(dtypes.keys())
    dict_keys(['_kind', '_active', '_step_fn', 'x', 'y', 'vx', 'vy', 'energy'])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class EntityKind:
    """Agent 类型描述符。

    声明该类型的 Agent 包含哪些属性列。在 register_kind() 时，
    EntityKind 被展开为 RECS EntityPool 的 attr_dtypes 字典。

    Attributes:
        name: 类型名（如 "prey"、"predator"）。
        position: 是否启用 2D 位置 (x, y float32)。
        position_3d: 是否启用 3D 位置（额外增加 z float32）。
        velocity: 是否启用速度向量 (vx, vy float32)。
        heading: 是否启用朝向角 (float32, 弧度)。
        speed: 是否启用速率标量 (float32)。
        energy: 是否启用能量 (float32)。
        age: 是否启用存活 tick 数 (int32)。
        color: 是否启用 RGB 颜色 (r,g,b uint8)。
        size: 是否启用显示大小 (float32)。
        team: 是否启用阵营 ID (int32)。
        group: 是否启用子群组 ID (int32)。
        state: 是否启用 FSM 状态 (int32)。
        state_timer: 是否启用当前状态持续 tick (int32)。
        custom: 用户自定义字段，dict[str, dtype]。
    """

    name: str

    # 预置属性组（按需启用，默认均关闭——不用的属性不占内存）
    position: bool = False
    position_3d: bool = False
    velocity: bool = False
    heading: bool = False
    speed: bool = False
    energy: bool = False
    age: bool = False
    color: bool = False
    size: bool = False
    team: bool = False
    group: bool = False
    state: bool = False
    state_timer: bool = False

    # 用户自定义字段: {"wealth": np.float32, "name": "U20"}
    custom: dict[str, Any] = field(default_factory=dict)


def _kind_to_dtypes(kind: EntityKind) -> dict[str, Any]:
    """将 EntityKind 展开为 RECS EntityPool 可消费的 dtype 字典。

    系统保留列（所有 kind 自动包含）：
    - _kind: U32 — kind 名称字符串
    - _active: bool — 激活标记
    - _step_fn: int32 — step 函数注册号（-1 表示未注册）

    预置属性按 EntityKind 的布尔开关逐一展开。
    自定义字段原样透传。

    Args:
        kind: EntityKind 实例。

    Returns:
        dict[str, dtype]: 可直接传给 EntityPool(attr_dtypes=...) 的字典。
    """
    dtypes: dict[str, Any] = {}

    # --- 系统保留列（所有 kind 共享） ---
    dtypes["_kind"] = "U32"
    dtypes["_active"] = np.bool_
    dtypes["_step_fn"] = np.int32

    # --- 预置属性展开 ---
    if kind.position:
        dtypes["x"] = np.float32
        dtypes["y"] = np.float32
    if kind.position_3d:
        dtypes["z"] = np.float32
    if kind.velocity:
        dtypes["vx"] = np.float32
        dtypes["vy"] = np.float32
    if kind.heading:
        dtypes["heading"] = np.float32
    if kind.speed:
        dtypes["speed"] = np.float32
    if kind.energy:
        dtypes["energy"] = np.float32
    if kind.age:
        dtypes["age"] = np.int32
    if kind.color:
        dtypes["r"] = np.uint8
        dtypes["g"] = np.uint8
        dtypes["b"] = np.uint8
    if kind.size:
        dtypes["size"] = np.float32
    if kind.team:
        dtypes["team"] = np.int32
    if kind.group:
        dtypes["group"] = np.int32
    if kind.state:
        dtypes["state"] = np.int32
    if kind.state_timer:
        dtypes["state_timer"] = np.int32

    # --- 自定义字段直通 ---
    dtypes.update(kind.custom)

    return dtypes
