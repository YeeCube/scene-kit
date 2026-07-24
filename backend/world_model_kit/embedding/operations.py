"""Embedding 操作 —— Entity 的动态宿主切换。

embed_to / detach / reattach 的底层实现。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world_model_kit.world import WorldModel


def embed_to(
    model: "WorldModel",
    kind: str,
    ids: np.ndarray,
    parent_kind: str,
    parent_ids: np.ndarray,
    method: str = "nearest",
) -> None:
    """将 entity 嵌入到新的 parent entity。

    修改 _parent_id 列，将当前位置投影到新 parent 的几何上。

    Args:
        model: WorldModel 实例。
        kind: 要迁移的 entity 的 kind 名称。
        ids: 目标 entity 索引。
        parent_kind: 新 parent 的 kind 名称。
        parent_ids: 新 parent entity 的索引（与 ids 等长）。
        method: 投影方法。"nearest"（最近点投影）。
    """
    if len(ids) == 0:
        return
    parent_pool = model._bridge.get_pool(parent_kind)
    child_pool = model._bridge.get_pool(kind)

    for i, child_id in enumerate(ids):
        parent_id = parent_ids[i]
        child_pool.d["_parent_id"][child_id] = parent_pool._entity_id_to_index(parent_id)


def detach(
    model: "WorldModel",
    kind: str,
    ids: np.ndarray,
) -> None:
    """脱离当前 parent，挂载到 root entity（_parent_id = -1）。

    Args:
        model: WorldModel 实例。
        kind: kind 名称。
        ids: 目标 entity 索引。
    """
    if len(ids) == 0:
        return
    pool = model._bridge.get_pool(kind)
    pool.d["_parent_id"][ids] = -1


def reattach(
    model: "WorldModel",
    kind: str,
    ids: np.ndarray,
    new_parent_kind: str,
    new_parent_ids: np.ndarray,
    method: str = "nearest",
) -> None:
    """重新挂载到新 parent —— detach + embed_to。

    Args:
        model: WorldModel 实例。
        kind: kind 名称。
        ids: 目标 entity 索引。
        new_parent_kind: 新 parent kind。
        new_parent_ids: 新 parent entity 索引。
        method: 投影方法。
    """
    detach(model, kind, ids)
    embed_to(model, kind, ids, new_parent_kind, new_parent_ids, method)
