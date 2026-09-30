"""从 RECS EntityPool 生成列式 WorldSnapshot。"""

from __future__ import annotations

import json
from typing import Any, Mapping, TYPE_CHECKING

import numpy as np

from scene_kit.geometry.hypergraph import HypergraphGeometry
from scene_kit.geometry.path import PathGeometry
from scene_kit.geometry.surface import SurfaceGeometry
from scene_kit.geometry.volume import VolumeGeometry
from scene_kit.protocol.types import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    SnapshotProjection,
    WorldSnapshot,
)
from scene_kit.protocol.validation import validate_snapshot

if TYPE_CHECKING:
    from scene_kit.world import WorldModel


_INTERNAL_COLUMNS = {"i", "o", "_kind", "_active", "_step_fn", "_parent_id", "_type"}


def _as_numpy(pool: Any, name: str) -> np.ndarray:
    arr = pool.d[name][: pool.size]
    if isinstance(arr, np.ndarray):
        return arr
    return np.asarray(pool.backend.to_numpy(arr))


def _native_column(values: np.ndarray) -> list[Any]:
    result = values.tolist()
    return result if isinstance(result, list) else [result]


def _schema_for(values: np.ndarray, *, semantic: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"dtype": str(values.dtype)}
    if values.ndim > 1:
        schema["shape"] = list(values.shape[1:])
    if semantic is not None:
        schema["semantic"] = semantic
    return schema


def _world_metadata(model: "WorldModel") -> dict[str, Any]:
    root = model._root_geometry
    if isinstance(root, SurfaceGeometry):
        return {
            "dimensions": 2,
            "coordinateSystem": "root-parametric",
            "bounds": {"u": [0.0, root.width], "v": [0.0, root.height]},
            "boundary": {"u": root.boundary_u, "v": root.boundary_v},
        }
    if isinstance(root, VolumeGeometry):
        return {
            "dimensions": 3,
            "coordinateSystem": "root-parametric",
            "bounds": {
                "u": [0.0, root.width],
                "v": [0.0, root.height],
                "w": [0.0, root.depth],
            },
        }
    if isinstance(root, PathGeometry):
        return {
            "dimensions": 1,
            "coordinateSystem": "network",
            "bounds": {"t": [0.0, root.total_length]},
            "structure": root.summary(),
        }
    if isinstance(root, HypergraphGeometry):
        return {
            "dimensions": None,
            "coordinateSystem": "hypergraph",
            "bounds": {},
            "structure": root.summary(),
        }
    return {"dimensions": None, "coordinateSystem": "unspecified", "bounds": {}}


def _visible_indices(
    model: "WorldModel", kind: str, projection: SnapshotProjection
) -> np.ndarray:
    active = model._lifecycle[kind].active_indices
    if len(active) == 0 or projection.viewport is None:
        return active
    pool = model._bridge.get_pool(kind)
    viewport = projection.viewport
    if "u" in pool.d and "v" in pool.d:
        u = _as_numpy(pool, "u")[active]
        v = _as_numpy(pool, "v")[active]
        mask = (
            (u >= viewport.get("u_min", -np.inf))
            & (u <= viewport.get("u_max", np.inf))
            & (v >= viewport.get("v_min", -np.inf))
            & (v <= viewport.get("v_max", np.inf))
        )
        return active[np.asarray(mask, dtype=bool)]
    # 结构 geometry 的空间范围裁剪（§3.8 结论 5）：按参数列区间
    for column, (low_key, high_key) in (
        ("t", ("t_min", "t_max")),
        ("vertex_id", ("vertex_min", "vertex_max")),
    ):
        if column in pool.d:
            values = _as_numpy(pool, column)[active].astype(np.float64)
            mask = (
                (values >= viewport.get(low_key, -np.inf))
                & (values <= viewport.get(high_key, np.inf))
            )
            return active[np.asarray(mask, dtype=bool)]
    return active


def _parent_uid_column(model: "WorldModel", kind: str, indices: np.ndarray) -> list[str | None]:
    definition = model._kind_defs[kind]
    parent_kind = definition.parent
    if parent_kind is None or parent_kind not in model._kind_defs:
        return [None] * len(indices)
    child_pool = model._bridge.get_pool(kind)
    parent_pool = model._bridge.get_pool(parent_kind)
    parent_indices = _as_numpy(child_pool, "_parent_id")[indices].astype(np.int64)
    parent_uids = _as_numpy(parent_pool, "i")
    result: list[str | None] = []
    for parent_index in parent_indices:
        if 0 <= parent_index < len(parent_uids):
            result.append(str(int(parent_uids[parent_index])))
        else:
            result.append(None)
    return result


def _relation_batches(
    model: "WorldModel", kinds: list[str], projection: SnapshotProjection
) -> dict[str, Any]:
    """把命名关系边表投影为列式 relationBatches（uid 十进制字符串编码）。"""
    batches: dict[str, Any] = {}
    if not projection.include_relations:
        return batches
    allowed = set(kinds)
    for name, record in model._relations.items():
        if record["srcKind"] not in allowed or record["dstKind"] not in allowed:
            continue
        rel = record["rel"]
        size = rel.size
        src_uids = np.asarray(rel.get_attr("src_uid")[:size], dtype=np.int64)
        dst_uids = np.asarray(rel.get_attr("dst_uid")[:size], dtype=np.int64)
        columns: dict[str, list[Any]] = {
            "srcUid": [str(int(value)) for value in src_uids],
            "dstUid": [str(int(value)) for value in dst_uids],
        }
        schema: dict[str, dict[str, Any]] = {
            "srcUid": {
                "dtype": "int64",
                "semantic": "edge-src-uid",
                "encoding": "decimal-string",
            },
            "dstUid": {
                "dtype": "int64",
                "semantic": "edge-dst-uid",
                "encoding": "decimal-string",
            },
        }
        for attr_name in rel.d:
            if attr_name in {"src_uid", "dst_uid"}:
                continue
            values = np.asarray(rel.get_attr(attr_name)[:size])
            columns[attr_name] = _native_column(values)
            schema[attr_name] = _schema_for(values)
        batches[name] = {
            "name": name,
            "srcKind": record["srcKind"],
            "dstKind": record["dstKind"],
            "count": size,
            "schema": schema,
            "columns": columns,
        }
    return batches


def build_snapshot(
    model: "WorldModel",
    projection: SnapshotProjection | Mapping[str, Any] | None = None,
) -> WorldSnapshot:
    """构建一个固定 schema 的 RECS 风格 SoA 快照。"""
    spec = SnapshotProjection.from_value(projection)
    available_kinds = model.list_kinds()
    kinds = [kind for kind in available_kinds if spec.kinds is None or kind in spec.kinds]
    entity_batches: dict[str, Any] = {}

    for kind in kinds:
        pool = model._bridge.get_pool(kind)
        definition = model._kind_defs[kind]
        indices = _visible_indices(model, kind, spec)
        default_columns = [name for name in pool.d if name not in _INTERNAL_COLUMNS and not name.startswith("_")]
        requested = spec.columns_for(kind, default_columns)
        columns: dict[str, list[Any]] = {}
        schema: dict[str, dict[str, Any]] = {}

        uid_values = _as_numpy(pool, "i")[indices].astype(np.int64, copy=False)
        columns["uid"] = [str(int(value)) for value in uid_values]
        schema["uid"] = {
            "dtype": "int64",
            "semantic": "entity-uid",
            "encoding": "decimal-string",
        }

        for name in requested:
            if name in {"uid", "parent_uid", "world_x", "world_y", "world_z"}:
                continue
            if name not in pool.d or name in _INTERNAL_COLUMNS or name.startswith("_"):
                continue
            values = _as_numpy(pool, name)[indices]
            columns[name] = _native_column(values)
            schema[name] = _schema_for(values)

        if definition.parent is not None:
            columns["parent_uid"] = _parent_uid_column(model, kind, indices)
            schema["parent_uid"] = {
                "dtype": "int64",
                "semantic": "parent-entity-uid",
                "encoding": "decimal-string",
                "nullable": True,
            }

        if spec.include_world_coordinates and len(indices) > 0:
            world_positions = np.asarray(model.resolve_world_position(kind, indices))
            labels = ("world_x", "world_y", "world_z")
            for axis in range(min(world_positions.shape[1], 3)):
                values = world_positions[:, axis]
                columns[labels[axis]] = _native_column(values)
                schema[labels[axis]] = _schema_for(values, semantic="world-coordinate")

        entity_batches[kind] = {
            "kind": kind,
            "geometry": definition.geometry,
            "dim": definition.dim,
            "role": definition.type,
            "parentKind": definition.parent,
            "count": len(indices),
            "schema": schema,
            "columns": columns,
        }

    metrics: dict[str, float] = {}
    if spec.include_metrics and model._collector is not None:
        metrics = model._collector.evaluate_metrics(model)

    snapshot: WorldSnapshot = {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "snapshotId": f"snapshot-{model._snapshot_sequence}",
        "tick": model.tick,
        "time": float(model.tick),
        "world": _world_metadata(model),
        "entityBatches": entity_batches,
        "relationBatches": _relation_batches(model, kinds, spec),
        "metrics": metrics,
    }
    validate_snapshot(snapshot)
    return snapshot


def export_snapshot(
    model: "WorldModel",
    projection: SnapshotProjection | Mapping[str, Any] | None = None,
    format: str = "dict",
) -> WorldSnapshot | bytes:
    """构建并编码 WorldSnapshot；不同编码保持同一逻辑 schema。"""
    model._snapshot_sequence += 1
    snapshot = build_snapshot(model, projection)
    if format == "dict":
        return snapshot
    if format == "json":
        return json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if format == "msgpack":
        try:
            import msgpack
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("使用 msgpack 格式需要安装 scene-kit[protocol]") from exc
        return msgpack.packb(snapshot, use_bin_type=True)
    raise ValueError("format 必须是 'dict'、'json' 或 'msgpack'")
