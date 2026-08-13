"""WorldSnapshot / WorldDelta 的轻量运行时校验。"""

from __future__ import annotations

from typing import Any, Mapping

from scene_kit.protocol.types import PROTOCOL_NAME, PROTOCOL_VERSION


class ProtocolValidationError(ValueError):
    """协议结构不满足 WMK schema。"""


def _validate_batch(name: str, batch: Mapping[str, Any]) -> None:
    count = batch.get("count")
    if not isinstance(count, int) or count < 0:
        raise ProtocolValidationError(f"batch '{name}' 的 count 必须是非负整数")
    columns = batch.get("columns")
    if not isinstance(columns, Mapping):
        raise ProtocolValidationError(f"batch '{name}' 缺少 columns")
    for column_name, values in columns.items():
        if not isinstance(values, list):
            raise ProtocolValidationError(
                f"batch '{name}' 的列 '{column_name}' 必须是 list"
            )
        if len(values) != count:
            raise ProtocolValidationError(
                f"batch '{name}' 的列 '{column_name}' 长度 {len(values)} != count {count}"
            )
    uids = columns.get("uid")
    if uids is None:
        raise ProtocolValidationError(f"entity batch '{name}' 缺少 uid 列")
    if any(not isinstance(uid, str) for uid in uids):
        raise ProtocolValidationError(f"entity batch '{name}' 的 uid 必须使用字符串编码")
    if len(set(uids)) != len(uids):
        raise ProtocolValidationError(f"entity batch '{name}' 的 uid 不唯一")


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """校验快照 envelope 与所有列长度。成功时返回 None。"""
    if snapshot.get("protocol") != PROTOCOL_NAME:
        raise ProtocolValidationError("未知的 snapshot protocol")
    if snapshot.get("protocolVersion") != PROTOCOL_VERSION:
        raise ProtocolValidationError("不支持的 snapshot protocolVersion")
    if not isinstance(snapshot.get("tick"), int):
        raise ProtocolValidationError("tick 必须是整数")
    batches = snapshot.get("entityBatches")
    if not isinstance(batches, Mapping):
        raise ProtocolValidationError("entityBatches 必须是对象")
    for name, batch in batches.items():
        if not isinstance(batch, Mapping):
            raise ProtocolValidationError(f"batch '{name}' 必须是对象")
        _validate_batch(str(name), batch)


def validate_delta(delta: Mapping[str, Any]) -> None:
    """校验 WorldDelta 的基础 envelope。"""
    if delta.get("protocol") != "wmk.world-delta":
        raise ProtocolValidationError("未知的 delta protocol")
    if delta.get("protocolVersion") != PROTOCOL_VERSION:
        raise ProtocolValidationError("不支持的 delta protocolVersion")
    if not isinstance(delta.get("baseSnapshotId"), str):
        raise ProtocolValidationError("baseSnapshotId 必须是字符串")
