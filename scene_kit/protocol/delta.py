"""列式 WorldSnapshot 差异计算。"""

from __future__ import annotations

from typing import Any, Mapping

from scene_kit.protocol.types import PROTOCOL_VERSION, WorldDelta, WorldSnapshot
from scene_kit.protocol.validation import validate_snapshot


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
        "protocol": "wmk.world-delta",
        "protocolVersion": PROTOCOL_VERSION,
        "baseSnapshotId": previous["snapshotId"],
        "snapshotId": current["snapshotId"],
        "tick": current["tick"],
        "time": current.get("time"),
        "world": current.get("world", {}),
        "entityBatches": changes,
        "relationBatches": {},
        "metrics": current.get("metrics", {}),
    }
