"""HypergraphGeometry —— 离散超图（无连续维度，拓扑类结构）。

主设计 §3.2：hypergraph 的自身维度为"离散"（dim=-1），自由度是顶点集，
为 children 提供离散超边约束。位置列是 ``vertex_id``（int64，entity_kind
预留列），实体"在哪"即"挂在哪个顶点上"。

语义口径（第一版）：
- 距离 = 关联图上的**跳数**（两个顶点共边记 1 跳；经由超边的成员关系传播）。
- 无自然连续位移：``move`` 按"顶点索引平移并取整钳制"实现（仅保证列值合法，
  真正的离散移动请用 set_attr 换 vertex_id 或行为层的随机游走）。
- 坐标解析（param_to_local）需要显式嵌入声明 + 顶点坐标，否则只给拓扑查询
  （与 path 同一口径，§3.8 结论 2）。
"""

from __future__ import annotations

from collections import deque
from typing import Sequence

import numpy as np

from scene_kit.geometry.base import Geometry
from scene_kit.geometry.embedding import Embedding

__all__ = ["HypergraphGeometry"]


class HypergraphGeometry(Geometry):
    """离散超图 geometry。

    Attributes:
        dim: -1.0（离散，无连续维度）。
    """

    dim: float = -1.0

    def __init__(
        self,
        vertices: Sequence[Sequence[float]] | np.ndarray | None = None,
        hyperedges: Sequence[Sequence[int]] | None = None,
        embedding: Embedding | None = None,
    ) -> None:
        if vertices is not None and len(vertices) > 0:
            self._coords = np.atleast_2d(np.asarray(vertices, dtype=np.float64))
        else:
            self._coords = np.zeros((0, 2), dtype=np.float64)
        self._edges: list[tuple[int, ...]] = []
        self._embedding = embedding
        self._hop_cache: dict[int, np.ndarray] = {}
        for edge in hyperedges or []:
            self.add_hyperedge(edge)

    # ------------------------------------------------------------------
    # 结构构建
    # ------------------------------------------------------------------

    def add_vertex(self, coords: Sequence[float] | None = None) -> int:
        """新增顶点（可带声明空间坐标），返回顶点索引。"""
        if coords is None:
            point = np.zeros((1, self._coords.shape[1]), dtype=np.float64)
        else:
            point = np.asarray(coords, dtype=np.float64).reshape(1, -1)
        self._coords = np.vstack([self._coords, point])
        self._hop_cache.clear()
        return int(len(self._coords) - 1)

    def add_hyperedge(self, members: Sequence[int], weight: float = 1.0) -> int:
        """新增超边（顶点索引集合），返回超边索引。"""
        member_tuple = tuple(int(m) for m in members)
        if any(m < 0 or m >= len(self._coords) for m in member_tuple):
            raise IndexError(f"超边引用了不存在的顶点: {member_tuple}")
        self._edges.append(member_tuple)
        self._hop_cache.clear()
        return len(self._edges) - 1

    @property
    def embedding(self) -> Embedding | None:
        return self._embedding

    @property
    def vertex_count(self) -> int:
        return int(len(self._coords))

    @property
    def edge_count(self) -> int:
        return int(len(self._edges))

    def members_of(self, edge_id: int) -> tuple[int, ...]:
        return self._edges[edge_id]

    def edges_of(self, vertex_id: int) -> list[int]:
        """包含该顶点的所有超边索引。"""
        return [i for i, members in enumerate(self._edges) if vertex_id in members]

    def summary(self) -> dict:
        return {
            "vertices": self.vertex_count,
            "hyperedges": self.edge_count,
            "space": self._embedding.space if self._embedding else None,
            "unit": self._embedding.unit if self._embedding else None,
            "metric": "hop",
        }

    # ------------------------------------------------------------------
    # 拓扑查询（不需要嵌入）
    # ------------------------------------------------------------------

    def hop_distances(self, source: int) -> np.ndarray:
        """顶点 source 到所有顶点的最小跳数（超边传播：共边即一跳）。"""
        cached = self._hop_cache.get(source)
        if cached is not None:
            return cached
        dist = np.full(self.vertex_count, np.inf)
        dist[source] = 0
        queue = deque([source])
        while queue:
            vertex = queue.popleft()
            for edge_id in self.edges_of(vertex):
                for member in self._edges[edge_id]:
                    if dist[member] > dist[vertex] + 1:
                        dist[member] = dist[vertex] + 1
                        queue.append(member)
        self._hop_cache[source] = dist
        return dist

    # ------------------------------------------------------------------
    # Geometry 接口
    # ------------------------------------------------------------------

    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """跳数距离（不可达记 inf）。"""
        pv = np.atleast_1d(np.asarray(p, dtype=np.float64).ravel()).astype(np.int64)
        qv = np.atleast_1d(np.asarray(q, dtype=np.float64).ravel()).astype(np.int64)
        out = np.full((len(pv), len(qv)), np.inf)
        for i, source in enumerate(pv):
            if 0 <= source < self.vertex_count:
                row = self.hop_distances(int(source))
                for j, target in enumerate(qv):
                    if 0 <= target < self.vertex_count:
                        out[i, j] = row[target]
        return out

    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """离散结构无自然位移：索引平移后取整钳制（保列值合法）。"""
        pos = np.atleast_2d(np.asarray(positions, dtype=np.float64))
        dlt = np.atleast_2d(np.asarray(delta, dtype=np.float64))
        moved = np.round(pos + dlt * dt).astype(np.float64)
        if self.vertex_count:
            moved[:, 0] = np.clip(moved[:, 0], 0, self.vertex_count - 1)
        else:
            moved[:, 0] = 0.0
        return moved

    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """跳数半径搜索：对每个查询顶点，返回跳数 < radius 的候选索引。"""
        dist = self.metric(positions, query_points)
        return [np.where(dist[:, j] < radius)[0] for j in range(dist.shape[1])]

    def contains(self, positions: np.ndarray) -> np.ndarray:
        pos = np.atleast_2d(np.asarray(positions, dtype=np.float64))
        idx = pos[:, 0]
        valid = np.equal(idx, np.round(idx))
        return valid & (idx >= 0) & (idx < self.vertex_count)

    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """顶点索引 → 声明空间坐标；需要嵌入声明且顶点带坐标。"""
        if self._embedding is None:
            raise RuntimeError(
                "HypergraphGeometry.param_to_local() 需要显式嵌入声明（Embedding）；"
                "未声明时本结构只提供拓扑类查询（§3.8 结论 2）。"
            )
        pos = np.atleast_1d(np.asarray(positions, dtype=np.float64).ravel())
        out = np.zeros((len(pos), 3), dtype=np.float32)
        for i, raw in enumerate(pos):
            vertex = int(round(raw))
            if 0 <= vertex < self.vertex_count:
                coords = self._coords[vertex]
                out[i, : coords.shape[0]] = coords[:3]
        return out
