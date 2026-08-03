"""VolumeGeometry —— 3D UVW 参数体。

三维欧几里得空间的几何实现。
"""

from __future__ import annotations

import numpy as np

from world_model_kit.geometry.base import Geometry


class VolumeGeometry(Geometry):
    """3D 立方体参数几何。

    Attributes:
        dim: 3.0。
        width: U 方向范围 [0, width]。
        height: V 方向范围 [0, height]。
        depth: W 方向范围 [0, depth]。
    """

    dim: float = 3.0

    def __init__(
        self,
        width: float = 100.0,
        height: float = 100.0,
        depth: float = 100.0,
    ) -> None:
        self.width = float(width)
        self.height = float(height)
        self.depth = float(depth)

    # ------------------------------------------------------------------
    # Geometry 接口
    # ------------------------------------------------------------------

    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """3D 欧几里得距离。"""
        p = np.atleast_2d(p)
        q = np.atleast_2d(q)
        diff = p[:, np.newaxis, :3] - q[np.newaxis, :, :3]
        return np.sqrt(np.sum(diff * diff, axis=-1))

    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """直接位置增量。"""
        p = np.atleast_2d(positions).astype(np.float32).copy()
        d = np.atleast_2d(np.asarray(delta, dtype=np.float32))
        p[:, :3] += d[:, :3] * dt
        return p

    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """3D 半径搜索。"""
        positions = np.atleast_2d(positions)
        query_points = np.atleast_2d(query_points)
        result: list[np.ndarray] = []
        for qp in query_points:
            diff = positions[:, :3] - qp[:3]
            dist = np.sqrt(np.sum(diff * diff, axis=-1))
            result.append(np.where(dist < radius)[0])
        return result

    def contains(self, positions: np.ndarray) -> np.ndarray:
        """检查是否在立方体范围内。"""
        p = np.atleast_2d(positions)
        return (p[:, 0] >= 0) & (p[:, 0] <= self.width) & \
               (p[:, 1] >= 0) & (p[:, 1] <= self.height) & \
               (p[:, 2] >= 0) & (p[:, 2] <= self.depth)

    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """UVW → (u, v, w) 笛卡尔坐标。"""
        p = np.atleast_2d(positions).astype(np.float32)
        return p[:, :3]
