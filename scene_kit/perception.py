"""Perception 感知框架 —— Agent 的结构化感知数据结构。

当 EntityKind 声明 perceive 字段时，step 函数接收 Perception 而非 ids。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Perception:
    """Agent 在一次 tick 中可获取的全部结构化感知信息。

    所有字段均为 NumPy 数组——与 RECS pool.d 同源，零拷贝。

    Attributes:
        self_tags: 自身 tags 的值。{"energy": array([45.2, ...]), ...}
        neighbors: target_kind → 邻域 entity 索引数组。{"predator": array([3,17,42]), ...}
        fields: 场名 → 当前位置场值（远期，当前为空字典）。
        collisions: 碰撞/接触的 entity 索引（radius ≈ 0）。
    """

    self_tags: dict[str, np.ndarray] = field(default_factory=dict)
    neighbors: dict[str, np.ndarray] = field(default_factory=dict)
    fields: dict[str, np.ndarray] = field(default_factory=dict)
    collisions: dict[str, np.ndarray] = field(default_factory=dict)
