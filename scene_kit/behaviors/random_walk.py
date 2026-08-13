"""random_walk —— 随机游走内置行为。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from scene_kit.world import WorldModel


def random_walk(model: "WorldModel", kind: str, step_size: float = 1.0) -> None:
    """注册随机游走 step 函数。

    Args:
        model: WorldModel 实例。
        kind: kind 名称。
        step_size: 每步移动的标量距离。
    """

    @model.step_for(kind)
    def _random_walk_step(m: "WorldModel", ids: np.ndarray) -> None:
        active = m._lifecycle[kind].active_indices
        ids_active = np.intersect1d(ids, active)
        if len(ids_active) == 0:
            return
        angle = np.random.uniform(0, 2 * np.pi, len(ids_active))
        # 移到 surface geometry 的 u/v
        delta_u = np.cos(angle) * step_size
        delta_v = np.sin(angle) * step_size
        delta = np.column_stack([delta_u, delta_v])
        m.move(kind, ids_active, delta)
