"""PointGeometry —— 0 维质点。

质点本身不提供空间约束——所有操作委托给 parent 的 geometry。
Point 的 move 只是简单的位置增量。
"""

from __future__ import annotations

import numpy as np

from world_model_kit.geometry.base import Geometry


class PointGeometry(Geometry):
    """0 维质点 geometry。

    质点的 dim=0，不提供空间约束。所有空间查询委托给 parent。
    """

    dim: float = 0.0

    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """欧几里得距离（p 的维度由 parent 决定）。"""
        diff = p[:, np.newaxis, :] - q[np.newaxis, :, :]
        return np.sqrt(np.sum(diff * diff, axis=-1))

    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """直接位置增量。"""
        return positions + np.asarray(delta, dtype=np.float32) * dt

    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """欧几里得半径搜索。"""
        result = []
        for qp in query_points:
            diff = positions - qp
            dist = np.sqrt(np.sum(diff * diff, axis=-1))
            result.append(np.where(dist < radius)[0])
        return result

    def contains(self, positions: np.ndarray) -> np.ndarray:
        """质点始终"在内部"。"""
        return np.ones(len(positions), dtype=bool)

    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """质点的参数坐标就是局部坐标，补齐到 3D。"""
        p = np.atleast_2d(positions)
        if p.shape[1] >= 3:
            return p[:, :3].astype(np.float32)
        if p.shape[1] == 2:
            z = np.zeros((len(p), 1), dtype=np.float32)
            return np.hstack([p, z])
        if p.shape[1] == 1:
            rest = np.zeros((len(p), 2), dtype=np.float32)
            return np.hstack([p, rest])
        return np.zeros((len(p), 3), dtype=np.float32)
