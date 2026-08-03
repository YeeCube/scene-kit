"""flocking —— Boids 群集行为。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world_model_kit.world import WorldModel


def flocking(
    model: "WorldModel",
    kind: str,
    separation: float = 1.5,
    alignment: float = 1.0,
    cohesion: float = 1.0,
    radius: float = 5.0,
    max_speed: float = 2.0,
) -> None:
    """注册 Boids 三规则群集 step 函数。

    Args:
        model: WorldModel 实例。
        kind: kind 名称。
        separation: 分离权重。
        alignment: 对齐权重。
        cohesion: 凝聚权重。
        radius: 感知半径。
        max_speed: 最大速度。
    """

    @model.step_for(kind)
    def _flocking_step(m: "WorldModel", ids: np.ndarray) -> None:
        pool = m._bridge.get_pool(kind)
        u = pool.d["u"][ids].astype(np.float64)
        v = pool.d["v"][ids].astype(np.float64)
        n = len(ids)

        new_du = np.zeros(n, dtype=np.float64)
        new_dv = np.zeros(n, dtype=np.float64)

        for i in range(n):
            du = u - u[i]
            dv = v - v[i]
            dist = np.sqrt(du**2 + dv**2)
            neighbors = (dist > 0) & (dist < radius)

            if neighbors.sum() < 2:
                continue

            nu = u[neighbors]
            nv = v[neighbors]

            # 分离
            close = dist[neighbors] < radius * 0.3
            if close.any():
                cdu = du[neighbors][close]
                cdv = dv[neighbors][close]
                cd = dist[neighbors][close] + 1e-6
                new_du[i] += (-cdu / cd).mean() * separation
                new_dv[i] += (-cdv / cd).mean() * separation

            # 凝聚
            new_du[i] += (nu.mean() - u[i]) * cohesion * 0.01
            new_dv[i] += (nv.mean() - v[i]) * cohesion * 0.01

        # 限速
        speed = np.sqrt(new_du**2 + new_dv**2)
        mask = speed > max_speed
        new_du[mask] *= max_speed / speed[mask]
        new_dv[mask] *= max_speed / speed[mask]

        m.move(kind, ids, np.column_stack([new_du, new_dv]))
