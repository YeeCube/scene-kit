"""PathGeometry / Embedding / road_map 适配器测试（任务 T1.1 + T1.2）。"""
import numpy as np
import pytest

from scene_kit import EntityKind, WorldModel
from scene_kit.geometry import Embedding, PathGeometry

PIXEL = Embedding(space="pixel", unit="px", metric="euclidean", dims=2)


def _cross_network():
    """十字网络：中心节点 0 连接四个端点 1-4，每臂长 10。

    节点坐标 (x, y)：0=(10,10) 1=(0,10) 2=(20,10) 3=(10,0) 4=(10,20)
    边：(0,1) (0,2) (0,3) (0,4)，弧长拼接顺序即边表顺序。
    """
    nodes = [(10, 10), (0, 10), (20, 10), (10, 0), (10, 20)]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4)]
    return PathGeometry(nodes=nodes, edges=edges, embedding=PIXEL)


class TestEmbeddingDeclaration:
    def test_unknown_metric_rejected(self):
        with pytest.raises(ValueError):
            Embedding(space="geo", metric="haversine")

    def test_bad_dims_rejected(self):
        with pytest.raises(ValueError):
            Embedding(space="pixel", dims=4)

    def test_topological_only_without_embedding(self):
        """无嵌入声明：拓扑查询可用，几何查询全部拒绝（§3.8 结论 2）。"""
        nodes = [(0, 0), (10, 0)]
        geo = PathGeometry(nodes=nodes, edges=[(0, 1)])  # 不声明 embedding
        assert geo.edge_of(np.array([0.0]))[0] == 0       # 拓扑：参数归属
        assert len(geo.adjacency()) == 2                   # 拓扑：邻接
        with pytest.raises(RuntimeError):
            geo.metric(np.array([0.0]), np.array([5.0]))   # 几何：拒绝
        with pytest.raises(RuntimeError):
            geo.param_to_local(np.array([1.0]))            # 几何：拒绝
        with pytest.raises(RuntimeError):
            geo.route(0.0, 5.0)                            # 几何：拒绝


class TestPathParameterization:
    def test_total_length_and_edge_lookup(self):
        geo = _cross_network()
        assert geo.total_length == pytest.approx(40.0)
        assert geo.edge_of(5.0)[0] == 0          # 第一臂内
        assert geo.edge_of(15.0)[0] == 1         # 第二臂（偏移 10 起）
        assert geo.local_offset(15.0)[0] == pytest.approx(5.0)

    def test_contains(self):
        geo = _cross_network()
        inside = geo.contains(np.array([[0.0], [39.9]]))
        outside = geo.contains(np.array([[40.0], [-1.0]]))
        assert inside.all() and not outside.any()

    def test_param_to_local_midpoints(self):
        geo = _cross_network()
        # t=5 在第一臂中点：(5, 10)
        local = geo.param_to_local(np.array([5.0]))
        assert np.allclose(local[0, :2], [5.0, 10.0])
        # t=15 在第二臂中点：(15, 10)
        local = geo.param_to_local(np.array([15.0]))
        assert np.allclose(local[0, :2], [15.0, 10.0])


class TestNetworkMetricAndMove:
    def test_metric_within_edge(self):
        geo = _cross_network()
        d = geo.metric(np.array([[2.0]]), np.array([[7.0]]))
        assert d[0, 0] == pytest.approx(5.0)

    def test_metric_across_junction(self):
        """两臂上的点经中心节点取网络最短距离。

        注：臂的起点即中心（t=0/10/20/30 均落在中心），臂端为区间内侧。
        """
        geo = _cross_network()
        # t=0.5（第一臂，距中心 0.5）到 t=19.5（第二臂，距中心 9.5）
        d = geo.metric(np.array([[0.5]]), np.array([[19.5]]))
        assert d[0, 0] == pytest.approx(10.0)

    def test_move_clamps_at_junction(self):
        """move 只在当前边内：过交叉点不自动选路（决策归行为层）。"""
        geo = _cross_network()
        pos = np.array([[8.0]])     # 第一臂内，距中心 2
        moved = geo.move(pos, np.array([[5.0]]))
        assert moved[0, 0] == pytest.approx(10.0)   # 钳制在边末端（中心）

    def test_move_backward_clamps_at_edge_start(self):
        geo = _cross_network()
        pos = np.array([[2.0]])
        moved = geo.move(pos, np.array([[-5.0]]))
        assert moved[0, 0] == pytest.approx(0.0)

    def test_neighborhood_by_network_distance(self):
        geo = _cross_network()
        # 查询点 t=5（第一臂中点 (5,10)）：4.5/5.5 距离 0.5；
        # 15 在第二臂中点，经中心距离 10；25 在第三臂经中心 20。
        positions = np.array([[5.5], [15.0], [4.5], [25.0]])
        hits = geo.neighborhood(positions, np.array([[5.0]]), 2.0)
        assert sorted(hits[0]) == [0, 2]

    def test_route_across_junction(self):
        geo = _cross_network()
        r = geo.route(5.0, 35.0)   # 第一臂中点 → 第四臂中点，经中心
        assert r["distance"] == pytest.approx(10.0)
        assert r["edge_ids"][0] == 0 and r["edge_ids"][-1] == 3
        assert r["via_nodes"] == [0]


class TestCurvedEdges:
    def test_polyline_edge_length(self):
        """带拐点的边：长度按折线累加。"""
        nodes = [(0, 0), (10, 10)]
        geo = PathGeometry(
            nodes=nodes,
            edges=[(0, 1, [(0, 10)])],  # (0,0)→(0,10)→(10,10)：10+10=20
            embedding=PIXEL,
        )
        assert geo.total_length == pytest.approx(20.0)
        local = geo.param_to_local(np.array([5.0]))
        assert np.allclose(local[0, :2], [0.0, 5.0])


class TestWorldIntegration:
    def _model_with_road_kind(self):
        m = WorldModel(seed=1)
        m.add_root_path(
            nodes=[(10, 10), (0, 10), (20, 10)],
            edges=[(0, 1), (0, 2)],
            embedding=PIXEL,
        )
        return m

    def test_register_path_kind_and_inject(self):
        m = self._model_with_road_kind()
        m.register_kind(EntityKind("car", geometry="path"))
        geo = PathGeometry(
            nodes=[(10, 10), (0, 10), (20, 10)],
            edges=[(0, 1), (0, 2)],
            embedding=PIXEL,
        )
        m.set_geometry("car", geo)
        ids = m.spawn("car", 2, t=[5.0, 15.0])
        assert m.attr("car", "t")[ids].tolist() == [5.0, 15.0]

    def test_move_and_resolve(self):
        m = self._model_with_road_kind()
        m.register_kind(EntityKind("car", geometry="path"))
        m.set_geometry("car", m._root_geometry)
        ids = m.spawn("car", 2, t=[5.0, 15.0])
        m.move("car", ids, np.array([[3.0], [3.0]]))
        # 5→8（边内），15→18（边内）
        assert m.attr("car", "t")[ids].tolist() == pytest.approx([8.0, 18.0])
        world = m.resolve_world_position("car", ids)
        # t=8：第一臂 (10,10)→(0,10) 内 8 → (2,10)；t=18：第二臂 (10,10)→(20,10) 内 8 → (18,10)
        assert np.allclose(world[0, :2], [2.0, 10.0])
        assert np.allclose(world[1, :2], [18.0, 10.0])

    def test_set_geometry_requires_kind(self):
        m = WorldModel(seed=1)
        with pytest.raises(KeyError):
            m.set_geometry("ghost", PathGeometry())


class TestRoadMapAdapter:
    def test_build_path_geometry_from_roads_dict(self):
        """合成提取结果（不依赖图像依赖）→ 适配器 → 网络可查询。"""
        from scene_kit.importers.road_map import build_path_geometry

        roads = {
            "junctions": {0: (10, 10), 1: (10, 0), 2: (0, 10)},
            "edges": {
                0: {"id": 0, "endpoints": (0, 1),
                    "pixels": [(10, 9), (10, 8), (10, 1)]},
                1: {"id": 1, "endpoints": (0, 2), "pixels": []},
            },
        }
        geo = build_path_geometry(roads)
        assert geo.embedding.space == "pixel"
        # 边 0：(10,10)→(10,9)→(10,8)→(10,1)→(10,0)（行=10 固定，列从 10→0），长 10
        assert geo.total_length == pytest.approx(10.0 + 10.0)
        # 显式声明覆盖默认
        geo2 = build_path_geometry(
            roads, embedding=Embedding(space="world", unit="m")
        )
        assert geo2.embedding.space == "world"
