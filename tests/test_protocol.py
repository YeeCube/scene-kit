"""v0.3.0 SoA 协议与交互会话测试。"""

from __future__ import annotations

import json

import numpy as np

from scene_kit import EntityKind, ModelSession, SnapshotProjection, WorldModel
from scene_kit.protocol import diff_snapshots, validate_delta, validate_snapshot


def make_model(config=None) -> WorldModel:
    config = dict(config or {})
    model = WorldModel(seed=7)
    model.add_root_surface(float(config.get("width", 20)), float(config.get("height", 10)))
    model.register_kind(
        EntityKind(
            "particle",
            geometry="point",
            tags={"energy": np.float32, "vx": np.float32},
        )
    )
    model.spawn(
        "particle",
        n=3,
        u=np.array([1, 2, 15], dtype=np.float32),
        v=np.array([3, 4, 5], dtype=np.float32),
        energy=np.array([10, 20, 30], dtype=np.float32),
        vx=1.0,
        r=20,
        g=100,
        b=200,
    )
    return model


def test_snapshot_is_soa_and_uses_stable_uid() -> None:
    model = make_model()
    snapshot = model.export_snapshot(format="dict")
    validate_snapshot(snapshot)
    batch = snapshot["entityBatches"]["particle"]
    assert batch["count"] == 3
    assert set(("uid", "u", "v", "energy")) <= set(batch["columns"])
    assert all(isinstance(uid, str) for uid in batch["columns"]["uid"])
    pool_uids = [str(int(value)) for value in model.get_pool("particle").d["i"][:3]]
    assert batch["columns"]["uid"] == pool_uids
    assert batch["columns"]["uid"] != ["0", "1", "2"]


def test_snapshot_projection_applies_one_selection_to_every_column() -> None:
    model = make_model()
    projection = SnapshotProjection(
        columns={"particle": ["u", "v", "energy"]},
        viewport={"u_min": 0, "u_max": 5, "v_min": 0, "v_max": 10},
    )
    batch = model.export_snapshot(projection, format="dict")["entityBatches"]["particle"]
    assert batch["count"] == 2
    assert all(len(values) == 2 for values in batch["columns"].values())
    assert "vx" not in batch["columns"]


def test_snapshot_json_preserves_same_schema() -> None:
    model = make_model()
    decoded = json.loads(model.export_snapshot(format="json"))
    validate_snapshot(decoded)
    assert isinstance(decoded["entityBatches"]["particle"]["columns"], dict)


def test_recs_o_is_lifecycle_source_of_truth() -> None:
    model = make_model()
    ids = model._lifecycle["particle"].active_indices
    model.get_pool("particle").remove(ids[:1])
    assert model._lifecycle["particle"].active_count == 2
    snapshot = model.export_snapshot(format="dict")
    assert snapshot["entityBatches"]["particle"]["count"] == 2


def test_delta_is_keyed_by_kind_and_uid() -> None:
    model = make_model()
    before = model.export_snapshot(format="dict")
    ids = model._lifecycle["particle"].active_indices
    model.move("particle", ids[:1], np.array([[1.0, 0.0]], dtype=np.float32))
    model.kill("particle", ids[1:2])
    after = model.export_snapshot(format="dict")
    delta = diff_snapshots(before, after)
    validate_delta(delta)
    change = delta["entityBatches"]["particle"]
    assert len(change["removedUids"]) == 1
    assert len(change["changed"]["uids"]) == 1
    assert "u" in change["changed"]["columns"]


def test_model_session_controls_and_uid_commands() -> None:
    session = ModelSession(make_model(), model_factory=make_model, parameters={"width": 20})
    play = session.dispatch({"type": "play", "commandId": "play-1"})
    assert play.accepted and session.playing
    session.advance()
    assert session.model.tick == 1
    pause = session.dispatch({"type": "pause", "commandId": "pause-1"})
    assert pause.accepted and not session.playing
    uid = session.snapshot()["entityBatches"]["particle"]["columns"]["uid"][0]
    result = session.dispatch(
        {
            "type": "set_tag",
            "commandId": "tag-1",
            "payload": {"kind": "particle", "uids": [uid], "field": "energy", "values": [99]},
        }
    )
    assert result.accepted
    assert float(session.model.attr("particle", "energy")[0]) == 99.0
    bad = session.dispatch(
        {
            "type": "set_tag",
            "commandId": "bad-1",
            "payload": {"kind": "particle", "uids": [uid], "field": "_active", "values": [False]},
        }
    )
    assert not bad.accepted


def test_model_session_can_edit_exposed_columns() -> None:
    session = ModelSession(make_model())
    uid = session.snapshot()["entityBatches"]["particle"]["columns"]["uid"][0]
    result = session.dispatch({"type": "set_attribute", "payload": {"kind": "particle", "uids": [uid], "field": "u", "values": [9]}})
    assert result.accepted
    assert float(session.model.attr("particle", "u")[0]) == 9
