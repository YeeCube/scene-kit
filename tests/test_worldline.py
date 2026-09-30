"""世界线地基与结构几何收口测试（任务 T1 余项 / T1.3 / T1.4 / T2.1–T2.3）。"""
import numpy as np

from scene_kit import EntityKind, WorldModel
from scene_kit.geometry import (
    Embedding,
    HypergraphGeometry,
    PathGeometry,
)
from scene_kit.runner import ModelSession

PIXEL = Embedding(space="pixel", unit="px", metric="euclidean", dims=2)


def _make_world(with_relations: bool = True):
    model = WorldModel(seed=7)
    model.add_root_surface(100, 100)
    model.register_kind(EntityKind("field", geometry="surface", type="ENV"))
    model.register_kind(EntityKind(
        "car", geometry="point", parent="field",
        tags={"speed": np.float32, "team": np.int32},
    ))
    field_ids = model.spawn("field", 1, u=[0.0], v=[0.0])
    car_ids = model.spawn("car", 3, u=[10.0, 20.0, 30.0], v=[5.0, 5.0, 5.0],
                          speed=[1.0, 2.0, 3.0], team=[0, 1, 0])
    model.embed_to("car", car_ids, "field", np.repeat(field_ids, 3))
    if with_relations:
        model.bind(
            "is_on", "car", "field",
            np.asarray([0, 1]), np.asarray([0, 0]),
            attrs_weight=np.asarray([0.5, 1.5], dtype=np.float32),
        )
    for _ in range(4):
        model.step()
    return model


class TestRehydrate:
    def test_roundtrip_preserves_state(self):
        model = _make_world()
        snapshot = model.export_snapshot(format="dict")
        restored = WorldModel.from_snapshot(snapshot)

        assert restored.tick == model.tick == 4
        assert restored.list_kinds() == model.list_kinds()
        src = snapshot["entityBatches"]["car"]["columns"]
        dst = restored.export_snapshot(format="dict")["entityBatches"]["car"]["columns"]
        assert dst["uid"] == src["uid"]
        assert np.allclose(dst["u"], src["u"])
        assert np.allclose(dst["speed"], src["speed"])
        assert dst["parent_uid"] == src["parent_uid"]
        # 关系（含边属性列）
        rel_batches = restored.export_snapshot(format="dict")["relationBatches"]
        assert rel_batches["is_on"]["count"] == 2
        assert np.allclose(rel_batches["is_on"]["columns"]["attrs_weight"],
                           [0.5, 1.5])

    def test_restored_world_can_step_forward(self):
        model = _make_world()
        snapshot = model.export_snapshot(format="dict")
        restored = WorldModel.from_snapshot(snapshot)
        restored.step()
        assert restored.tick == 5
        # 隔离性：原模型 tick 不受影响
        assert model.tick == 4

    def test_snapshot_with_path_kind_carries_structure_meta(self):
        model = WorldModel(seed=1)
        root = model.add_root_path(
            nodes=[(0, 0), (10, 0)], edges=[(0, 1)], embedding=PIXEL)
        model.register_kind(EntityKind("walker", geometry="path"))
        model.set_geometry("walker", root)
        model.spawn("walker", 2, t=[2.0, 8.0])
        snapshot = model.export_snapshot(format="dict")
        assert snapshot["world"]["coordinateSystem"] == "network"
        assert snapshot["world"]["structure"]["edges"] == 1
        # T1.4：结构 kind 的空间范围裁剪（弧长区间）
        trimmed = model.export_snapshot(
            {"viewport": {"t_min": 5.0}}, format="dict")
        uids = trimmed["entityBatches"]["walker"]["columns"]["uid"]
        all_uids = snapshot["entityBatches"]["walker"]["columns"]["uid"]
        assert uids == [all_uids[1]]      # 仅保留 t=8 的第二个实体


class TestWorldlineFork:
    def test_session_default_is_autostart(self):
        session = ModelSession(WorldModel())
        assert session.playing is True            # Always-On 默认（§12.5）
        legacy = ModelSession(WorldModel(), autostart=False)
        assert legacy.playing is False

    def test_fork_isolates_and_inherits_tick(self):
        session = ModelSession(_make_world(), autostart=False)
        session.advance(steps=2, force=True)     # tick 4 → 6
        child = session.fork()

        assert child.model.tick == session.model.tick == 6
        assert child.playing is False
        assert child.name.endswith("@fork#6")
        assert child.capabilities["fork"] is True

        uid = session.snapshot()["entityBatches"]["car"]["columns"]["uid"][0]
        session.dispatch({
            "type": "set_attribute",
            "payload": {"kind": "car", "uids": [uid], "field": "speed",
                        "values": [99.0]},
        })
        assert float(session.model.attr("car", "speed")[0]) == 99.0
        assert float(child.model.attr("car", "speed")[0]) == 1.0   # 分叉隔离

    def test_fork_from_any_snapshot_node(self):
        """世界线分支：从非当前态的历史快照分叉。"""
        model = _make_world()
        old_node = model.export_snapshot(format="dict")   # tick 4
        model.step(); model.step()                        # tick 6
        session = ModelSession(model, autostart=False)
        child = session.fork(old_node)
        assert child.model.tick == 4
        assert session.model.tick == 6


class TestHypergraph:
    def _triangle(self):
        # 顶点 0/1/2；超边 e0={0,1}, e1={1,2}：0→2 距离 2 跳
        return HypergraphGeometry(
            vertices=[(0, 0), (10, 0), (10, 10)],
            hyperedges=[[0, 1], [1, 2]],
            embedding=PIXEL,
        )

    def test_hop_metric_and_neighborhood(self):
        geo = self._triangle()
        d = geo.metric(np.array([[0.0]]), np.array([[2.0]]))
        assert d[0, 0] == 2.0
        hits = geo.neighborhood(np.array([[0.0], [1.0], [2.0]]),
                                np.array([[0.0]]), 1.5)
        assert sorted(hits[0]) == [0, 1]

    def test_contains_and_move_legality(self):
        geo = self._triangle()
        assert geo.contains(np.array([[1.0], [3.0], [1.4]])).tolist() == \
            [True, False, False]
        moved = geo.move(np.array([[1.0]]), np.array([[5.0]]))
        assert moved[0, 0] == 2.0                 # 取整并钳制

    def test_param_to_local(self):
        geo = self._triangle()
        local = geo.param_to_local(np.array([2.0]))
        assert np.allclose(local[0, :2], [10.0, 10.0])

    def test_topology_only_without_embedding(self):
        geo = HypergraphGeometry(vertices=[(0, 0), (1, 0)],
                                 hyperedges=[[0, 1]])
        assert geo.edge_count == 1
        assert geo.hop_distances(0)[1] == 1.0
        try:
            geo.param_to_local(np.array([0.0]))
            raise AssertionError("应拒绝")
        except RuntimeError:
            pass

    def test_world_integration_with_vertex_id(self):
        model = WorldModel(seed=3)
        model.register_kind(EntityKind("member", geometry="hypergraph"))
        geo = HypergraphGeometry(vertices=[(0, 0), (5, 0)],
                                 hyperedges=[[0, 1]], embedding=PIXEL)
        model.set_geometry("member", geo)
        ids = model.spawn("member", 2, vertex_id=[0, 1])
        world = model.resolve_world_position("member", ids)
        assert np.allclose(world[1, :2], [5.0, 0.0])
        # T1.4：按顶点范围裁剪
        snap = model.export_snapshot({"viewport": {"vertex_min": 1}},
                                     format="dict")
        assert snap["entityBatches"]["member"]["columns"]["vertex_id"] == [1]


class TestWithinRadiusStructural:
    def test_within_radius_on_path(self):
        model = WorldModel(seed=1)
        root = model.add_root_path(
            nodes=[(0, 0), (10, 0)], edges=[(0, 1)], embedding=PIXEL)
        model.register_kind(EntityKind("walker", geometry="path"))
        model.set_geometry("walker", root)
        ids = model.spawn("walker", 3, t=[1.0, 4.0, 9.0])
        hits = model.within_radius("walker", ids, 4.2, 0.0, 1.0)
        assert ids[hits].tolist() == [1]          # t=4 → (4,0) 距 (4.2,0) 0.2
