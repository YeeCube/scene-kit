"""pursuit_evasion —— 追捕-逃跑行为。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world_model_kit.world import WorldModel


def pursuit_evasion(
    model: "WorldModel",
    pursuer_kind: str,
    evader_kind: str,
    capture_radius: float = 2.0,
    pursuit_speed: float = 1.5,
) -> None:
    """注册追捕-逃跑 step 函数。

    Args:
        model: WorldModel 实例。
        pursuer_kind: 追捕者 kind。
        evader_kind: 逃跑者 kind。
        capture_radius: 捕获半径。
        pursuit_speed: 追捕速度。
    """

    @model.step_for(pursuer_kind)
    def _pursuer_step(m: "WorldModel", ids: np.ndarray) -> None:
        evader_lm = m._lifecycle.get(evader_kind)
        if evader_lm is None or evader_lm.active_count == 0:
            return
        evader_ids = evader_lm.active_indices
        pu = m.attr(pursuer_kind, "u")[ids]
        pv = m.attr(pursuer_kind, "v")[ids]
        eu = m.attr(evader_kind, "u")[evader_ids]
        ev = m.attr(evader_kind, "v")[evader_ids]

        for i, pid in enumerate(ids):
            dists = np.sqrt((eu - pu[i])**2 + (ev - pv[i])**2)
            nearest_j = np.argmin(dists)
            nearest_id = evader_ids[nearest_j]
            if dists[nearest_j] < capture_radius:
                m.kill(evader_kind, np.array([nearest_id]))
            else:
                du = eu[nearest_j] - pu[i]
                dv = ev[nearest_j] - pv[i]
                d = max(dists[nearest_j], 1e-6)
                m.move(pursuer_kind, np.array([pid]),
                       np.array([[du / d * pursuit_speed, dv / d * pursuit_speed]]))

    @model.step_for(evader_kind)
    def _evader_step(m: "WorldModel", ids: np.ndarray) -> None:
        pursuer_lm = m._lifecycle.get(pursuer_kind)
        if pursuer_lm is None or pursuer_lm.active_count == 0:
            return
        pursuer_ids = pursuer_lm.active_indices
        eu = m.attr(evader_kind, "u")[ids]
        ev = m.attr(evader_kind, "v")[ids]
        pu = m.attr(pursuer_kind, "u")[pursuer_ids]
        pv = m.attr(pursuer_kind, "v")[pursuer_ids]

        for i, eid in enumerate(ids):
            dists = np.sqrt((pu - eu[i])**2 + (pv - ev[i])**2)
            nearest_j = np.argmin(dists)
            du = eu[i] - pu[nearest_j]
            dv = ev[i] - pv[nearest_j]
            d = max(dists[nearest_j], 1e-6)
            m.move(evader_kind, np.array([eid]),
                   np.array([[du / d * 1.0, dv / d * 1.0]]))
