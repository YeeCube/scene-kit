"""从 WorldSnapshot 水合出可继续演化的 WorldModel（世界线节点 → 会话初始态）。

主设计 §12.3：SK 核心只提供 ``from_snapshot()`` 水合入口；世界线树结构
（父子、标签、注释）归上层存档库。本模块是纯数据操作：
快照的列式批次 → 注册 kind → spawn 保 uid → 回填列 → 恢复 parent/关系 → 对齐 tick。

水合保证（fork/回退正确性的前提）：
- uid 逐字保留（十进制字符串 → int64 覆写 ``i`` 列）；
- tick 对齐到快照记录值，可继续 step；
- 关系边按 (srcUid, dstUid) 重放 ``bind``；
- 快照外的会话态（选择集、playing）不属于 interchange，不恢复。
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import numpy as np

from scene_kit.entity_kind import _GEOMETRY_POSITION_COLS

if TYPE_CHECKING:
    from scene_kit.world import WorldModel

_NON_TAG_COLUMNS = {"uid", "parent_uid", "world_x", "world_y", "world_z"}


def _dtype_from_schema(schema: dict[str, Any]) -> np.dtype:
    dtype = np.dtype(str(schema.get("dtype", "float64")))
    if schema.get("shape"):
        raise ValueError(
            "水合暂不支持多列数组属性（schema.shape 非空）；"
            "请在投影时用 columns 裁掉该列。"
        )
    return dtype


def _topo_order(batches: dict[str, Any]) -> list[str]:
    """按 parentKind 依赖排序 kind（父先子后，容环退化为原序）。"""
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(name: str, guard: int = 0) -> None:
        if name in seen or guard > len(batches):
            return
        seen.add(name)
        parent = batches[name].get("parentKind")
        if parent in batches:
            visit(parent, guard + 1)
        ordered.append(name)

    for name in batches:
        visit(name)
    return ordered


def snapshot_to_model(
    snapshot: dict[str, Any],
    model: "WorldModel | None" = None,
) -> "WorldModel":
    """把快照水合为 WorldModel（新对象或由调用方提供的目标对象）。

    Args:
        snapshot: ``build_snapshot`` / ``export_snapshot(format="dict")`` 产物。
        model: 可选的既有模型（将叠加注册）；None 时新建 WorldModel。

    Returns:
        WorldModel：uid、列值、parent、关系与 tick 均已恢复，可继续 step。
    """
    from scene_kit.entity_kind import EntityKind
    from scene_kit.world import WorldModel

    target = model if model is not None else WorldModel()

    # 根几何：按 world 元数据重建 root（surface/volume）
    world_meta = snapshot.get("world", {})
    bounds = world_meta.get("bounds") or {}
    if world_meta.get("coordinateSystem") == "root-parametric":
        if world_meta.get("dimensions") == 2 and "u" in bounds and "v" in bounds:
            target.add_root_surface(bounds["u"][1] - bounds["u"][0],
                                    bounds["v"][1] - bounds["v"][0])
        elif world_meta.get("dimensions") == 3 and "w" in bounds:
            target.add_root_volume(bounds["u"][1] - bounds["u"][0],
                                   bounds["v"][1] - bounds["v"][0],
                                   bounds["w"][1] - bounds["w"][0])

    entity_batches: dict[str, Any] = snapshot.get("entityBatches", {})
    order = _topo_order(entity_batches)

    # 1) 注册 kind（tags = 非位置、非保留列）
    for kind_name in order:
        if kind_name in target.list_kinds():
            continue
        batch = entity_batches[kind_name]
        geometry = str(batch.get("geometry", "point"))
        position_cols = {name for name, _ in _GEOMETRY_POSITION_COLS.get(geometry, [])}
        tags: dict[str, Any] = {}
        for column_name, schema in (batch.get("schema") or {}).items():
            if column_name in _NON_TAG_COLUMNS or column_name in position_cols:
                continue
            tags[column_name] = _dtype_from_schema(schema)
        target.register_kind(EntityKind(
            kind_name,
            geometry=geometry,
            dim=float(batch.get("dim", 0.0)),
            type=str(batch.get("role", "AGENT")),
            parent=batch.get("parentKind"),
            tags=tags,
        ))

    # 2) spawn 并保 uid、回填列
    uid_lists: dict[str, np.ndarray] = {}
    for kind_name in order:
        batch = entity_batches[kind_name]
        columns = batch.get("columns", {})
        uids = np.asarray([int(value) for value in columns.get("uid", [])],
                          dtype=np.int64)
        count = int(batch.get("count", len(uids)))
        if count == 0:
            uid_lists[kind_name] = uids
            continue
        pool = target.get_pool(kind_name)
        indices = target.spawn(kind_name, n=count)
        pool.d["i"][indices] = uids
        uid_lists[kind_name] = uids
        for column_name, values in columns.items():
            if column_name == "uid" or column_name == "parent_uid":
                continue
            if column_name.startswith("world_"):
                continue
            if column_name not in pool.d:
                continue
            array = pool.d[column_name]
            dtype = array.dtype if isinstance(array, np.ndarray) else np.asarray(array).dtype
            array[indices] = np.asarray(values, dtype=dtype)

    # 3) 恢复 parent（uid → index）
    for kind_name in order:
        batch = entity_batches[kind_name]
        parent_uids = (batch.get("columns") or {}).get("parent_uid")
        if not parent_uids or batch.get("parentKind") is None:
            continue
        parent_kind = str(batch["parentKind"])
        parent_uids_array = uid_lists.get(parent_kind)
        if parent_uids_array is None:
            continue
        lookup = {int(uid): index for index, uid in enumerate(parent_uids_array)}
        pool = target.get_pool(kind_name)
        active = target._lifecycle[kind_name].active_indices
        for row, parent_uid in zip(active, parent_uids):
            if parent_uid is None or str(parent_uid).lower() == "none":
                continue
            parent_index = lookup.get(int(parent_uid))
            if parent_index is not None:
                pool.d["_parent_id"][row] = parent_index

    # 4) 重放关系边
    for name, record in (snapshot.get("relationBatches") or {}).items():
        columns = record.get("columns", {})
        src_uids = columns.get("srcUid", [])
        dst_uids = columns.get("dstUid", [])
        if not src_uids:
            continue
        attrs: dict[str, Any] = {}
        for column_name, values in columns.items():
            if column_name in {"srcUid", "dstUid"}:
                continue
            attrs[column_name] = np.asarray(values)
        target.bind(
            name,
            str(record["srcKind"]),
            str(record["dstKind"]),
            np.asarray([int(value) for value in src_uids], dtype=np.int64),
            np.asarray([int(value) for value in dst_uids], dtype=np.int64),
            **attrs,
        )

    # 5) 对齐 tick（水合后可从该节点继续演化）
    target._tick = int(snapshot.get("tick", 0))
    return target
