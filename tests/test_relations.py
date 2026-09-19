"""v0.7.0 关系投影测试：bind/unbind、快照投影、关系差异与协议命名空间。"""

from __future__ import annotations

import numpy as np

from scene_kit import EntityKind, SnapshotProjection, WorldModel
from scene_kit.protocol import diff_snapshots, validate_snapshot


def make_model() -> WorldModel:
    model = WorldModel(seed=7)
    model.add_root_surface(20, 10)
    model.register_kind(EntityKind("piece", geometry="point", tags={"energy": np.float32}))
    model.register_kind(EntityKind("slot", geometry="point", tags={"energy": np.float32}))
    model.spawn("piece", n=2, u=np.array([1.0, 2.0]), v=np.array([1.0, 1.0]))
    model.spawn("slot", n=3, u=np.array([5.0, 6.0, 7.0]), v=np.array([5.0, 5.0, 5.0]))
    return model


def uids(model: WorldModel, kind: str) -> np.ndarray:
    pool = model.get_pool(kind)
    return np.asarray(pool.d["i"][: pool.size], dtype=np.int64)


def test_bind_projects_columnar_relation_batch() -> None:
    model = make_model()
    count = model.bind(
        "is_on",
        "piece",
        "slot",
        uids(model, "piece"),
        uids(model, "slot")[:2],
        weight=np.array([1.5, 2.5], dtype=np.float32),
    )
    assert count == 2
    assert model.relations()["is_on"] == {"srcKind": "piece", "dstKind": "slot", "count": 2}

    snapshot = model.export_snapshot(format="dict")
    validate_snapshot(snapshot)
    assert snapshot["protocol"] == "scene-kit.world-snapshot"
    assert snapshot["protocolVersion"] == "1.1"
    batch = snapshot["relationBatches"]["is_on"]
    assert batch["srcKind"] == "piece"
    assert batch["count"] == 2
    assert batch["columns"]["srcUid"] == [str(int(u)) for u in uids(model, "piece")]
    assert batch["columns"]["weight"] == [1.5, 2.5]
    assert batch["schema"]["srcUid"]["semantic"] == "edge-src-uid"
    assert batch["schema"]["dstUid"]["semantic"] == "edge-dst-uid"


def test_bind_dedupes_edges_and_unbind_removes_by_uid() -> None:
    model = make_model()
    src = uids(model, "piece")
    dst = uids(model, "slot")[:2]
    model.bind("is_on", "piece", "slot", src, dst)
    assert model.bind("is_on", "piece", "slot", src, dst) == 2
    remaining = model.unbind("is_on", src_uids=src[:1])
    assert remaining == 1
    batch = model.export_snapshot(format="dict")["relationBatches"]["is_on"]
    assert batch["columns"]["srcUid"] == [str(int(src[1]))]
    assert batch["columns"]["dstUid"] == [str(int(dst[1]))]


def test_delta_reports_added_and_removed_relation_edges() -> None:
    model = make_model()
    src = uids(model, "piece")
    dst = uids(model, "slot")
    model.bind("is_on", "piece", "slot", src[:1], dst[:1])
    before = model.export_snapshot(format="dict")

    model.bind("is_on", "piece", "slot", src[1:], dst[1:2])
    model.unbind("is_on", src_uids=src[:1])
    after = model.export_snapshot(format="dict")

    delta = diff_snapshots(before, after)
    change = delta["relationBatches"]["is_on"]
    assert change["removedEdges"] == [[str(int(src[0])), str(int(dst[0]))]]
    assert change["added"]["count"] == 1
    assert change["added"]["columns"]["srcUid"] == [str(int(src[1]))]
    assert change["changed"]["edges"] == []


def test_projection_can_exclude_relations() -> None:
    model = make_model()
    model.bind("is_on", "piece", "slot", uids(model, "piece"), uids(model, "slot")[:2])
    snapshot = model.export_snapshot(SnapshotProjection(include_relations=False), format="dict")
    assert snapshot["relationBatches"] == {}


def test_projection_kinds_filter_drops_other_endpoints() -> None:
    model = make_model()
    model.bind("is_on", "piece", "slot", uids(model, "piece"), uids(model, "slot")[:2])
    snapshot = model.export_snapshot(SnapshotProjection(kinds=["slot"]), format="dict")
    assert "is_on" not in snapshot["relationBatches"]
    assert "slot" in snapshot["entityBatches"]
