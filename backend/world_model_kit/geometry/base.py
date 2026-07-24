"""Geometry 抽象基类。

定义所有 geometry 类型必须实现的统一接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Geometry(ABC):
    """所有 geometry 的抽象基类。

    Attributes:
        dim: 内在维度（0=point, 1=path, 2=surface, 3=volume, -1=hypergraph）。
    """

    dim: float = 0.0

    @abstractmethod
    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """计算 p 和 q 之间的距离。

        Args:
            p: shape=(n, d) 的第一组点。
            q: shape=(m, d) 的第二组点。

        Returns:
            shape=(n, m) 的成对距离矩阵。
        """
        ...

    @abstractmethod
    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """沿 delta 方向移动 positions。

        Args:
            positions: shape=(n, d) 的当前位置（参数坐标）。
            delta: shape=(n, d) 的位移向量。
            dt: 时间步长。

        Returns:
            shape=(n, d) 的新位置（参数坐标）。
        """
        ...

    @abstractmethod
    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """在 query_points 的半径内搜索 positions。

        Args:
            positions: shape=(n, d) 的候选位置。
            query_points: shape=(m, d) 的查询中心。
            radius: 搜索半径。

        Returns:
            list of length m，每个元素是半径内的 positions 索引数组。
        """
        ...

    @abstractmethod
    def contains(self, positions: np.ndarray) -> np.ndarray:
        """检查 positions 是否在几何范围内。

        Args:
            positions: shape=(n, d) 的待检查位置。

        Returns:
            shape=(n,) 的布尔数组。
        """
        ...

    @abstractmethod
    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """将参数坐标转换为局部笛卡尔坐标。

        Args:
            positions: shape=(n, d) 的参数坐标。

        Returns:
            shape=(n, 3) 的局部笛卡尔坐标 (x, y, z)。
        """
        ...
