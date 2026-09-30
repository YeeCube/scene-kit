"""PathGeometry —— 折线网络（1D 结构，可在节点间步进/路由）。

主设计 §3.2：path 的自身维度为 1，children 的约束是「1D 网络」。
本实现采用**全局弧长参数化**：把网络按边展开为区间拼接
``[0, L)``，实体位置列即单列 ``t``（弧长坐标，entity_kind 已预留）。
边身份可由 t 反查（searchsorted），节点/交叉点是边的区间端点。

设计口径（第一版，最简原型）：
- **度量与路由走网络**：两点距离 = 沿网络的最短路；跨交叉点时
  经节点图 Dijkstra（全对最短路在构建期一次性缓存，规模上限为千级节点）。
- **move 不自动选路**：位移只在当前边内前进、到区间端点即钳制——
  「过岔路口往哪边走」是决策而非几何，需要显式 route/travel 的语义时
  由行为层调用 route() 规划（本文档同步登记于任务 T1.2）。
- **无嵌入声明 = 只有拓扑**：embedding=None 时长度/距离/坐标解析全部
  拒绝，仅提供邻接与参数归属查询（§3.8 结论 2）。
"""

from __future__ import annotations

import bisect
import heapq
from collections.abc import Sequence

import numpy as np

from scene_kit.geometry.base import Geometry
from scene_kit.geometry.embedding import Embedding

__all__ = ["PathGeometry"]


class PathGeometry(Geometry):
    """折线网络 geometry。

    Args:
        nodes: shape=(n, dims) 的节点（交叉点/端点）坐标，按声明空间解释。
        edges: 边列表，元素为 ``(a, b)`` 节点索引（直线段），或
            ``(a, b, polyline)`` 带中间拐点序列（polyline 不含端点也可以含，
            内部会规整为 a→…→b 的有序点列）。
        embedding: 显式嵌入声明；None 表示只提供拓扑查询。

    Attributes:
        dim: 1.0（内在维度）。
    """

    dim: float = 1.0

    def __init__(
        self,
        nodes: Sequence[Sequence[float]] | np.ndarray | None = None,
        edges: Sequence[tuple] | None = None,
        embedding: Embedding | None = None,
    ) -> None:
        node_array = np.zeros((0, 2), dtype=np.float64)
        if nodes is not None and len(nodes) > 0:
            node_array = np.atleast_2d(np.asarray(nodes, dtype=np.float64))
        self._nodes = node_array
        self._embedding = embedding

        # 每条边规整为有序点列与累计弧长
        self._edge_polys: list[np.ndarray] = []
        self._edge_ends: list[tuple[int, int]] = []
        for edge in edges or []:
            a, b = int(edge[0]), int(edge[1])
            extra = edge[2] if len(edge) > 2 else None
            polyline = self._build_polyline(a, b, extra)
            self._edge_polys.append(polyline)
            self._edge_ends.append((a, b))

        self._edge_lengths = np.array(
            [_poly_length(p, _metric_of(embedding)) if embedding else 0.0
             for p in self._edge_polys],
            dtype=np.float64,
        )
        # 全局弧长区间起点偏移 o_e，拼接为 [0, L)
        self._edge_offsets = np.zeros(len(self._edge_polys) + 1, dtype=np.float64)
        if len(self._edge_lengths):
            self._edge_offsets[1:] = np.cumsum(self._edge_lengths)
        self._total_length = float(self._edge_offsets[-1])

        self._node_dist: np.ndarray | None = None
        self._adjacency: list[list[tuple[int, float]]] | None = None
        if embedding is not None and len(self._edge_polys):
            self._precompute_node_graph()

    # ------------------------------------------------------------------
    # 结构访问（拓扑类查询，不需要嵌入）
    # ------------------------------------------------------------------

    @property
    def embedding(self) -> Embedding | None:
        return self._embedding

    @property
    def total_length(self) -> float:
        """网络总弧长；无嵌入时为 0.0。"""
        return self._total_length

    @property
    def node_count(self) -> int:
        return int(len(self._nodes))

    @property
    def edge_count(self) -> int:
        return int(len(self._edge_polys))

    def adjacency(self) -> list[list[tuple[int, float]]]:
        """节点邻接表（node → [(neighbor, edge_id)]）。"""
        table: list[list[tuple[int, float]]] = [[] for _ in self._nodes]
        for edge_id, (a, b) in enumerate(self._edge_ends):
            table[a].append((b, edge_id))
            table[b].append((a, edge_id))
        return table

    def edge_of(self, t: np.ndarray | float) -> np.ndarray:
        """弧长坐标 t 所在的边索引。"""
        values = np.atleast_1d(np.asarray(t, dtype=np.float64))
        if not len(self._edge_polys):
            raise ValueError("空网络：没有边可归属。")
        # searchsorted(right)-1 并对最后一条边右端开放
        idx = np.clip(
            np.searchsorted(self._edge_offsets, values, side="right") - 1,
            0, len(self._edge_polys) - 1,
        )
        return idx

    def local_offset(self, t: np.ndarray | float) -> np.ndarray:
        """弧长坐标 t 在所属边内的局部弧长。"""
        values = np.atleast_1d(np.asarray(t, dtype=np.float64))
        return values - self._edge_offsets[self.edge_of(values)]

    def summary(self) -> dict:
        """结构摘要（供快照裁剪与调试；不含拐点级细节）。"""
        return {
            "nodes": int(self.node_count),
            "edges": int(self.edge_count),
            "total_length": self._total_length,
            "space": self._embedding.space if self._embedding else None,
            "unit": self._embedding.unit if self._embedding else None,
            "metric": self._embedding.metric if self._embedding else None,
        }

    # ------------------------------------------------------------------
    # Geometry 接口
    # ------------------------------------------------------------------

    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray:
        """网络最短距离（沿边走，跨交叉点经节点最短路）。"""
        self._require_embedding("metric")
        pt = np.atleast_1d(np.asarray(p, dtype=np.float64).ravel())
        qt = np.atleast_1d(np.asarray(q, dtype=np.float64).ravel())
        out = np.zeros((len(pt), len(qt)), dtype=np.float64)
        for i, tp in enumerate(pt):
            e_p = int(self.edge_of(tp)[0])
            s_p = float(self.local_offset(tp)[0])
            a_p, b_p = self._edge_ends[e_p]
            d_p = (s_p, self._edge_lengths[e_p] - s_p)  # 到 a、到 b
            for j, tq in enumerate(qt):
                e_q = int(self.edge_of(tq)[0])
                s_q = float(self.local_offset(tq)[0])
                a_q, b_q = self._edge_ends[e_q]
                d_q = (s_q, self._edge_lengths[e_q] - s_q)
                best = np.inf
                if e_p == e_q:
                    best = min(best, abs(s_p - s_q))
                for xp in (0, 1):
                    node_p = (a_p, b_p)[xp]
                    for xq in (0, 1):
                        node_q = (a_q, b_q)[xq]
                        via = d_p[xp] + self._node_dist[node_p, node_q] + d_q[xq]
                        best = min(best, via)
                out[i, j] = best
        return out

    def move(
        self,
        positions: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> np.ndarray:
        """当前边内位移，区间端点（交叉点）钳制；不自动跨节点选路。"""
        pos = np.atleast_2d(np.asarray(positions, dtype=np.float64))
        dlt = np.atleast_2d(np.asarray(delta, dtype=np.float64))
        t = pos[:, 0] + dlt[:, 0] * dt
        # 钳制区间按「当前所在边」计：越过区间端点停在交叉点上，不换边
        edges = self.edge_of(pos[:, 0])
        lo = self._edge_offsets[edges]
        hi = lo + self._edge_lengths[edges]
        moved = np.clip(t, lo, hi)
        return moved.reshape(-1, 1).astype(np.float32)

    def neighborhood(
        self,
        positions: np.ndarray,
        query_points: np.ndarray,
        radius: float,
    ) -> list[np.ndarray]:
        """网络距离半径搜索。"""
        self._require_embedding("neighborhood")
        dist = self.metric(positions, query_points)
        return [np.where(dist[:, j] < radius)[0]
                for j in range(dist.shape[1])]

    def contains(self, positions: np.ndarray) -> np.ndarray:
        """t 是否落在网络区间 [0, L) 内。"""
        pos = np.atleast_2d(np.asarray(positions, dtype=np.float64))
        return (pos[:, 0] >= 0.0) & (pos[:, 0] < self._total_length)

    def param_to_local(self, positions: np.ndarray) -> np.ndarray:
        """弧长坐标 t → 声明空间中的 (x, y, z) 局部坐标。"""
        self._require_embedding("param_to_local")
        t = np.atleast_1d(np.asarray(positions, dtype=np.float64).ravel())
        t = np.clip(t, 0.0, max(self._total_length, 0.0))
        out = np.zeros((len(t), 3), dtype=np.float32)
        for i, tv in enumerate(t):
            edge_id = int(self.edge_of(tv)[0])
            s = float(self.local_offset(tv)[0])
            xy = _point_at_arclength(
                self._edge_polys[edge_id], s, self._embedding.metric
            )
            out[i, :2] = xy[:2]
            if self._nodes.shape[1] >= 3:
                out[i, 2] = self._edge_polys[edge_id][0, 2]
        return out

    # ------------------------------------------------------------------
    # 路由（供行为层显式选路）
    # ------------------------------------------------------------------

    def route(self, t_from: float, t_to: float) -> dict:
        """沿网络从 t_from 到 t_to 的最短路径规划。

        Returns:
            dict: {"distance", "via_nodes", "edge_ids"} —— via_nodes 为
            途经的节点索引序列（不含起止点所在边端点的重复项），
            edge_ids 为依次经过的边。
        """
        self._require_embedding("route")
        e_p = int(self.edge_of(t_from)[0])
        e_q = int(self.edge_of(t_to)[0])
        if e_p == e_q:
            return {
                "distance": float(abs(t_from - t_to)),
                "via_nodes": [],
                "edge_ids": [e_p],
            }
        a_p, b_p = self._edge_ends[e_p]
        a_q, b_q = self._edge_ends[e_q]
        s_p = float(self.local_offset(t_from)[0])
        s_q = float(self.local_offset(t_to)[0])
        d_p = (s_p, self._edge_lengths[e_p] - s_p)
        d_q = (s_q, self._edge_lengths[e_q] - s_q)
        best = (np.inf, None, None)
        for xp in (0, 1):
            for xq in (0, 1):
                total = d_p[xp] + self._node_dist[(a_p, b_p)[xp], (a_q, b_q)[xq]] + d_q[xq]
                if total < best[0]:
                    best = (total, xp, xq)
        _, xp, xq = best
        node_path = self._node_path((a_p, b_p)[xp], (a_q, b_q)[xq])
        edge_seq = [e_p]
        current = node_path[0]
        for nxt in node_path[1:]:
            edge_seq.append(self._edge_between(current, nxt))
            current = nxt
        if e_q not in edge_seq or edge_seq[-1] != e_q:
            edge_seq.append(e_q)
        return {
            "distance": float(best[0]),
            "via_nodes": [int(n) for n in node_path],
            "edge_ids": [int(e) for e in edge_seq],
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _require_embedding(self, what: str) -> None:
        if self._embedding is None:
            raise RuntimeError(
                f"PathGeometry.{what}() 需要显式嵌入声明（Embedding）；"
                "未声明时本网络只提供拓扑类查询（§3.8 结论 2）。"
            )

    def _build_polyline(self, a: int, b: int, extra) -> np.ndarray:
        points = [self._nodes[a]]
        if extra is not None and len(extra) > 0:
            for mid in np.atleast_2d(np.asarray(extra, dtype=np.float64)):
                points.append(mid)
        points.append(self._nodes[b])
        return np.asarray(points, dtype=np.float64)

    def _precompute_node_graph(self) -> None:
        """节点图全对最短路（千级节点内直接 Floyd 风格 Dijkstra）。"""
        n = self.node_count
        adjacency: list[list[tuple[int, float]]] = [[] for _ in range(n)]
        for edge_id, ((a, b), length) in enumerate(
            zip(self._edge_ends, self._edge_lengths)
        ):
            adjacency[a].append((b, float(length)))
            adjacency[b].append((a, float(length)))
        dist = np.full((n, n), np.inf)
        np.fill_diagonal(dist, 0.0)
        for source in range(n):
            _dijkstra(adjacency, source, dist[source])
        self._node_dist = dist
        self._adjacency = adjacency

    def _node_path(self, a: int, b: int) -> list[int]:
        """节点 a→b 的最短节点序列（含两端）。"""
        if a == b:
            return [a]
        assert self._adjacency is not None
        # 沿 _node_dist 贪心下降重建（对正权图成立）
        path = [a]
        current = a
        while current != b:
            neighbors = [
                (nb, w) for nb, w in self._adjacency[current]
                if np.isfinite(self._node_dist[nb, b])
            ]
            step = min(
                neighbors,
                key=lambda nb_w: nb_w[1] + self._node_dist[nb_w[0], b],
            )
            current = step[0]
            path.append(current)
            if len(path) > self.node_count + 1:  # 防御环
                break
        return path

    def _edge_between(self, a: int, b: int) -> int:
        for edge_id, (ea, eb) in enumerate(self._edge_ends):
            if (ea, eb) == (a, b) or (ea, eb) == (b, a):
                return edge_id
        raise KeyError(f"节点 {a}-{b} 之间没有边。")


# ----------------------------------------------------------------------
# 模块级工具
# ----------------------------------------------------------------------

def _metric_of(embedding: Embedding | None) -> str:
    return embedding.metric if embedding else "euclidean"


def _pair_distance(p: np.ndarray, q: np.ndarray, metric: str) -> float:
    diff = np.abs(p - q)
    if metric == "manhattan":
        return float(diff.sum())
    return float(np.sqrt((diff * diff).sum()))


def _poly_length(poly: np.ndarray, metric: str) -> float:
    if len(poly) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(poly)):
        total += _pair_distance(poly[i - 1], poly[i], metric)
    return total


def _point_at_arclength(poly: np.ndarray, s: float, metric: str = "euclidean") -> np.ndarray:
    """边内按弧长取点（段长与声明度规一致）。"""
    metric_segments = [
        _pair_distance(poly[i - 1], poly[i], metric)
        for i in range(1, len(poly))
    ]
    acc = 0.0
    for i, seg in enumerate(metric_segments):
        if acc + seg >= s or i == len(metric_segments) - 1:
            ratio = 0.0 if seg == 0 else min(max((s - acc) / seg, 0.0), 1.0)
            return poly[i] + ratio * (poly[i + 1] - poly[i])
        acc += seg
    return poly[-1]


def _dijkstra(adjacency: list[list[tuple[int, float]]], source: int, out: np.ndarray) -> None:
    """单源最短路，结果写入 out（长度与节点数等长）。"""
    out[source] = 0.0
    visited = np.zeros(len(out), dtype=bool)
    heap = [(0.0, source)]
    while heap:
        distance, node = heapq.heappop(heap)
        if visited[node]:
            continue
        visited[node] = True
        for neighbor, weight in adjacency[node]:
            candidate = distance + weight
            if candidate < out[neighbor]:
                out[neighbor] = candidate
                heapq.heappush(heap, (candidate, neighbor))
