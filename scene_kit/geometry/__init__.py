"""Geometry 子模块 —— 六种 geometry 的抽象基类与实现。

每个 geometry 实现以下接口：
- metric(p, q)          两点间的距离
- move(positions, delta) 沿方向移动
- neighborhood(positions, radius) 邻域搜索
- contains(positions)    点在不在几何里
- param_to_local(positions) 参数坐标→局部笛卡尔坐标
"""

from scene_kit.geometry.base import Geometry
from scene_kit.geometry.embedding import Embedding
from scene_kit.geometry.hypergraph import HypergraphGeometry
from scene_kit.geometry.path import PathGeometry
from scene_kit.geometry.point import PointGeometry
from scene_kit.geometry.surface import SurfaceGeometry
from scene_kit.geometry.volume import VolumeGeometry

__all__ = [
    "Geometry",
    "Embedding",
    "HypergraphGeometry",
    "PathGeometry",
    "PointGeometry",
    "SurfaceGeometry",
    "VolumeGeometry",
]
