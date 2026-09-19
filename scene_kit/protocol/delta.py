"""列式 WorldSnapshot 差异计算。"""

from __future__ import annotations

from typing import Any, Mapping

from scene_kit.protocol.types import (
    DELTA_PROTOCOL_NAME,
    PROTOCOL_VERSION,
    WorldDelta,
    WorldSnapshot,
)
from scene_kit.protocol.validation import validate_snapshot


def _edge_pairs(batch: Mapping[str, Any]) -> list[tuple[str, str]]:
    columns = batch["columns"]
    return list(zip(columns["srcUid"], columns["dstUid"]))


def _diff_relations(
    previous: WorldSnapshot, current: WorldSnapshot
) -> dict[str, Any]:
    """按关系名与 (srcUid, dstUid) 边身份计算 added/removed/changed。"""
    previous_batches = previous.get("relationBatches", {})
    current_batches = current.get("relationBatches", {})
    changes: dict[str, Any] = {}
    for name in sorted(set(previous_batches) | set(current_batches)):
        before = previous_batches.get(name)
        after = current_batches.get(name)
        if before is None:
            changes[name] = {
                "removedEdges": [],
                "added": after,
                "changed": {"edges": [], "columns": {}},
            }
            continue
        if after is None:
            changes[name] = {
                "removedEdges": [list(edge) for edge in _edge_pairs(before)],
                "added": None,
                "changed": {"edges": [], "columns": {}},
            }
            continue
        before_edges = _edge_pairs(before)
        after_edges = _edge_pairs(after)
        before_index = {edge: i for i, edge in enumerate(before_edges)}
        after_index = {edge: i for i, edge in enumerate(after_edges)}
        added_edges = [edge for edge in after_edges if edge not in before_index]
        removed_edges = [edge for edge in before_edges if edge not in after_index]
        comparable = sorted(
            (set(before["columns"]) & set(after["columns"])) - {"srcUid", "dstUid"}
        )
        changed_edges = [
            edge
            for edge in after_edges
            if edge in before_index
            and any(
                before["columns"][column][before_index[edge]]
                != after["columns"][column][after_index[edge]]
                for column in comparable
            )
        ]
        if not (added_edges or removed_edges or changed_edges):
            continue
        added = None
        if added_edges:
            positions = [after_index[edge] for edge in added_edges]
            added = {
                **{k: v for k, v in after.items() if k not in {"count", "columns"}},
                "count": len(positions),
                "columns": {
                    column: [values[i] for i in positions]
                    for column, values in after["columns"].items()
                },
            }
        changed_columns = {
            column: [after["columns"][column][after_index[edge]] for edge in changed_edges]
            for column in comparable
        }
        changes[name] = {
            "removedEdges": [list(edge) for edge in removed_edges],
            "added": added,
            "changed": {
                "edges": [list(edge) for edge in changed_edges],
                "columns": changed_columns,
            },
        }
    return changes


def _rows(columns: Mapping[str, list[Any]], indices: list[int]) -> dict[str, list[Any]]:
    return {name: [values[index] for index in indices] for name, values in columns.items()}


def diff_snapshots(previous: WorldSnapshot, current: WorldSnapshot) -> WorldDelta:
    """按 ``(kind, uid)`` 计算 added/removed/changed 列差异。"""
    validate_snapshot(previous)
    validate_snapshot(current)
    changes: dict[str, Any] = {}
    previous_batches = previous["entityBatches"]
    current_batches = current["entityBatches"]

    for kind in sorted(set(previous_batches) | set(current_batches)):
        before = previous_batches.get(kind)
        after = current_batches.get(kind)
        if before is None:
            changes[kind] = {
                "removedUids": [],
                "added": after,
                "changed": {"uids": [], "columns": {}},
            }
            continue
        if after is None:
            changes[kind] = {
                "removedUids": list(before["columns"]["uid"]),
                "added": None,
                "changed": {"uids": [], "columns": {}},
            }
            continue

        before_uids = list(before["columns"]["uid"])
        after_uids = list(after["columns"]["uid"])
        before_index = {uid: index for index, uid in enumerate(before_uids)}
        after_index = {uid: index for index, uid in enumerate(after_uids)}
        added_uids = [uid for uid in after_uids if uid not in before_index]
        removed_uids = [uid for uid in before_uids if uid not in after_index]
        added_indices = [after_index[uid] for uid in added_uids]

        comparable_columns = sorted(set(before["columns"]) & set(after["columns"]) - {"uid"})
        changed_uids: list[str] = []
        for uid in after_uids:
            if uid not in before_index:
                continue
            old_index = before_index[uid]
            new_index = after_index[uid]
            if any(
                before["columns"][name][old_index] != after["columns"][name][new_index]
                for name in comparable_columns
            ):
                changed_uids.append(uid)
        changed_indices = [after_index[uid] for uid in changed_uids]
        changed_columns = {
            name: [after["columns"][name][index] for index in changed_indices]
            for name in comparable_columns
        }

        if added_uids or removed_uids or changed_uids:
            added = None
            if added_indices:
                added = {
                    **{key: value for key, value in after.items() if key not in {"count", "columns"}},
                    "count": len(added_indices),
                    "columns": _rows(after["columns"], added_indices),
                }
            changes[kind] = {
                "removedUids": removed_uids,
                "added": added,
                "changed": {"uids": changed_uids, "columns": changed_columns},
            }

    return {
        "protocol": DELTA_PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "baseSnapshotId": previous["snapshotId"],
        "snapshotId": current["snapshotId"],
        "tick": current["tick"],
        "time": current.get("time"),
        "world": current.get("world", {}),
        "entityBatches": changes,
        "relationBatches": _diff_relations(previous, current),
        "metrics": current.get("metrics", {}),
    }
