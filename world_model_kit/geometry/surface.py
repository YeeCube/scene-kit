"""SurfaceGeometry —— 2D UV 参数网格。

最常用的 geometry 类型。等价于传统的 2D 连续空间。
支持 clamp / toroidal / bounce 三种边界模式。
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from world_model_kit.geometry.base import Geometry

BoundaryMode = Literal["clamp", "toroidal", "bounce", "none"]


class SurfaceGeometry(Geometry):
    """2D 矩形参数网格 geometry。

    Attributes:
        dim: 2.0（内在维度）。
        width: U 方向范围 [0, width]。
        height: V 方向范围 [0, height]。
        boundary_u: U 方向边界模式。
        boundary_v: V 方向边界模式。
    """

    dim: float = 2.0

    def __init__(
        self,
        width: float = 100.0,
        height: float = 100.0,
        boundary_u: BoundaryMode = "clamp",
        boundary_v: BoundaryMode = "clamp",
    ) -> None:
        self.width = float(width)
        self.height = float(height)
        self.boundary_u = boundary_u
        self.boundary_v = boundary_v

    def _apply_boundary(self, positions: np.ndarray) -> np.ndarray:
        """对所有位置应用边界模式。"""
        p = positions.copy()
        # U 方向
        if self.boundary_u == "clamp":
            np.clip(p[:, 0], 0.0, self.width, out=p[:, 0])
        elif self.boundary_u == "toroidal":
            p[:, 0] = p[:, 0] % self.width
        elif self.boundary_u == "bounce":
            over = p[:, 0] > self.width
            under = p[:, 0] < 0
            p[over, 0] = 2 * self.width - p[over, 0]
            p[under, 0] = -p[under, 0]
        # V 方向
        if self.boundary_v == "clamp":
            np.clip(p[:, 1], 0.0, self.height, out=p[:, 1])
        elif self.boundary_v == "toroidal":
            p[:, 1] = p[:, 1] % self.height
        elif self.boundary_v == "bounce":
            over = p[:, 1] > self.height
            under = p[:, 1] < 0
            p[over, 1] = 2 * self.height - p[over, 1]
            p[under, 1] = -p[under, 1]
        return p

    # ------------------------------------------------------------------
    # Geometry 接口
    # ------------------------------------------------------------------

    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """2D 欧几里得距离。"""
        p = np.atleast_2d(p)
        q = np.atleast_2d(q)
        diff = p[:, np.newaxis, :2] - q[np.newaxis, :, :2]
        return np.sqrt(np.sum(diff * diff, axis=-1))

    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """沿 delta 移动并应用边界。"""
        p = np.atleast_2d(positions).astype(np.float32).copy()
        d = np.atleast_2d(np.asarray(delta, dtype=np.float32))
        p[:, :2] += d[:, :2] * dt
        return self._apply_boundary(p)

    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """半径搜索。"""
        positions = np.atleast_2d(positions)
        query_points = np.atleast_2d(query_points)
        result: list[np.ndarray] = []
        if self.boundary_u == "toroidal" or self.boundary_v == "toroidal":
            # 环形距离需要特殊处理
            for qp in query_points:
                du = np.abs(positions[:, 0] - qp[0])
                dv = np.abs(positions[:, 1] - qp[1])
                if self.boundary_u == "toroidal":
                    du = np.minimum(du, self.width - du)
                if self.boundary_v == "toroidal":
                    dv = np.minimum(dv, self.height - dv)
                dist = np.sqrt(du * du + dv * dv)
                result.append(np.where(dist < radius)[0])
        else:
            for qp in query_points:
                diff = positions[:, :2] - qp[:2]
                dist = np.sqrt(np.sum(diff * diff, axis=-1))
                result.append(np.where(dist < radius)[0])
        return result

    def contains(self, positions: np.ndarray) -> np.ndarray:
        """检查是否在矩形范围内。"""
        p = np.atleast_2d(positions)
        return (p[:, 0] >= 0) & (p[:, 0] <= self.width) & \
               (p[:, 1] >= 0) & (p[:, 1] <= self.height)

    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """UV → (u, v, 0) 笛卡尔坐标。"""
        p = np.atleast_2d(positions).astype(np.float32)
        z = np.zeros((len(p), 1), dtype=np.float32)
        return np.hstack([p[:, :2], z])

    # ------------------------------------------------------------------
    # 便捷方法（供 WorldModel 的 clamp/wrap/bounce 调用）
    # ------------------------------------------------------------------

    def clamp(self, positions: np.ndarray) -> np.ndarray:
        """钳制到边界内。"""
        p = np.atleast_2d(positions).copy()
        np.clip(p[:, 0], 0.0, self.width, out=p[:, 0])
        np.clip(p[:, 1], 0.0, self.height, out=p[:, 1])
        return p

    def wrap_toroidal(self, positions: np.ndarray) -> np.ndarray:
        """环形环绕。"""
        p = np.atleast_2d(positions).copy()
        p[:, 0] = p[:, 0] % self.width
        p[:, 1] = p[:, 1] % self.height
        return p
