"""M2 测试：SelectionSet、批处理宏、关系命令与逻辑吸附（ADR-002 D2/D3）。"""

from __future__ import annotations

import numpy as np

from scene_kit import EntityKind, ModelSession, WorldModel


def make_session() -> ModelSession:
    model = WorldModel(seed=7)
    model.add_root_surface(20, 10)
    model.register_kind(EntityKind("piece", geometry="point", tags={"energy": np.float32}))
    model.register_kind(EntityKind("slot", geometry="point", tags={"energy": np.float32}))
    model.spawn(
        "piece",
        n=3,
        u=np.array([1.0, 2.0, 15.0], dtype=np.float32),
        v=np.array([1.0, 1.0, 5.0], dtype=np.float32),
    )
    model.spawn(
        "slot",
        n=2,
        u=np.array([5.0, 6.0], dtype=np.float32),
        v=np.array([5.0, 5.0], dtype=np.float32),
    )
    return ModelSession(model)


def uids(session: ModelSession, kind: str) -> list[str]:
    pool = session.model.get_pool(kind)
    return [str(int(value)) for value in pool.d["i"][: pool.size]]


def dispatch(session: ModelSession, command_type: str, **payload) -> dict:
    result = session.dispatch({"type": command_type, "payload": payload})
    assert result.accepted, result.error
    return dict(result.data)


def test_capabilities_advertise_new_commands() -> None:
    session = make_session()
    advertised = set(session.capabilities["commands"])
    assert {
        "select",
        "clear_selection",
        "get_selection",
        "batch_move",
        "batch_set_attribute",
        "bind_relation",
        "unbind_relation",
        "snap_to_slots",
    } <= advertised


def test_select_by_rect_add_and_clear() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    data = dispatch(session, "select", kind="piece", rect={"u_min": 0, "u_max": 3, "v_min": 0, "v_max": 2})
    assert sorted(data["selection"]["piece"]) == sorted(piece_uids[:2])

    data = dispatch(session, "select", kind="piece", uids=[piece_uids[2]], mode="add")
    assert sorted(data["selection"]["piece"]) == sorted(piece_uids)

    data = dispatch(session, "select", kind="piece", uids=[piece_uids[0]], mode="remove")
    assert data["selection"]["piece"] == piece_uids[1:]

    dispatch(session, "clear_selection")
    assert dispatch(session, "get_selection")["selection"] == {}


def test_batch_move_and_batch_set_attribute_apply_to_selection() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    dispatch(session, "select", kind="piece", uids=piece_uids[:2])

    dispatch(session, "batch_move", delta=[1.0, 0.0])
    pool = session.model.get_pool("piece")
    u_column = np.asarray(pool.d["u"][: pool.size], dtype=np.float64)
    assert u_column[0] == 2.0 and u_column[1] == 3.0 and u_column[2] == 15.0

    dispatch(session, "batch_set_attribute", field="energy", value=99.0)
    snapshot = session.snapshot()
    energy = snapshot["entityBatches"]["piece"]["columns"]["energy"]
    assert energy[0] == 99.0 and energy[1] == 99.0 and energy[2] != 99.0


def test_snap_to_slots_aligns_and_binds_relation() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    slot_uids = uids(session, "slot")
    # 把 0 号棋子挪到 0 号落点附近（5.2, 5.1），半径 0.5 内应吸附
    dispatch(session, "move", kind="piece", uids=[piece_uids[0]], delta=[4.2, 4.1])

    data = dispatch(session, "snap_to_slots", kind="piece", slotKind="slot", radius=0.5, uids=[piece_uids[0]])
    assert data["snapped"] == [{"uid": piece_uids[0], "slotUid": slot_uids[0]}]

    pool = session.model.get_pool("piece")
    assert float(pool.d["u"][0]) == 5.0 and float(pool.d["v"][0]) == 5.0
    assert session.model.relations()["is_on"]["count"] == 1

    batch = session.snapshot()["relationBatches"]["is_on"]
    assert batch["columns"]["srcUid"] == [piece_uids[0]]
    assert batch["columns"]["dstUid"] == [slot_uids[0]]


def test_snap_outside_radius_is_skipped() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    data = dispatch(session, "snap_to_slots", kind="piece", slotKind="slot", radius=0.5, uids=piece_uids)
    assert data["snapped"] == []
    assert sorted(data["skipped"]) == sorted(piece_uids)
    assert "is_on" not in session.model.relations()


def test_despawn_cascades_unbind_and_prunes_selection() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    slot_uids = uids(session, "slot")
    dispatch(session, "move", kind="piece", uids=[piece_uids[0]], delta=[4.2, 4.1])
    # 走选择集路径：先选中再吸附（不显式传 uids）
    dispatch(session, "select", kind="piece", uids=[piece_uids[0]])
    dispatch(session, "snap_to_slots", kind="piece", slotKind="slot", radius=0.5)
    dispatch(session, "select", kind="piece", uids=piece_uids[:2])

    dispatch(session, "despawn", kind="piece", uids=[piece_uids[0]])
    assert session.model.relations()["is_on"]["count"] == 0
    assert dispatch(session, "get_selection")["selection"]["piece"] == [piece_uids[1]]
    # 悬空边已清偿：快照中 is_on 为空批次
    assert session.snapshot()["relationBatches"]["is_on"]["count"] == 0
    assert slot_uids  # 落点不受影响


def test_bind_and_unbind_relation_commands() -> None:
    session = make_session()
    piece_uids = uids(session, "piece")
    slot_uids = uids(session, "slot")
    data = dispatch(
        session,
        "bind_relation",
        name="guards",
        srcKind="piece",
        dstKind="slot",
        srcUids=piece_uids[:2],
        dstUids=slot_uids[:2],
        attrs={"weight": np.array([1.0, 2.0], dtype=np.float32)},
    )
    assert data == {"name": "guards", "count": 2}

    data = dispatch(session, "unbind_relation", name="guards", srcUids=[piece_uids[0]])
    assert data == {"name": "guards", "count": 1}
