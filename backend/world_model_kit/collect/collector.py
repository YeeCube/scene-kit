"""DataCollector —— 仿真数据采集器。

按 tick 记录 agent 级字段和 population 级聚合，支持导出为 DataFrame。
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world_model_kit.world import WorldModel


class DataCollector:
    """仿真数据采集器。

    在每个 tick 结束后自动触发，按配置记录字段。

    Attributes:
        _agent_fields: kind → [(field_name, ...)] 的 agent 级记录配置。
        _aggregates: [(kind_field, ops)] 的聚合配置。
        _metrics: [(name, fn)] 的自定义指标配置。
        _snapshot_interval: 快照间隔 tick 数。
        _records: list[dict] 的逐 tick 记录。
    """

    def __init__(self) -> None:
        self._agent_fields: dict[str, list[str]] = {}
        self._aggregates: list[tuple[str, str, list[str]]] = []  # (kind, field, ops)
        self._metrics: list[tuple[str, Callable]] = []
        self._snapshot_interval: int = 0
        self._records: list[dict] = []

    # ------------------------------------------------------------------
    # 配置 API
    # ------------------------------------------------------------------

    def collect(self, kind: str, fields: list[str]) -> None:
        """记录指定 kind 的 agent 级字段。

        Args:
            kind: kind 名称。
            fields: 要记录的列名列表。
        """
        self._agent_fields[kind] = fields

    def aggregate(self, kind: str, field: str, ops: list[str]) -> None:
        """对指定 kind.field 进行 population 级聚合。

        Args:
            kind: kind 名称。
            field: 列名。
            ops: 聚合操作列表 ["mean", "std", "min", "max", "sum", "count"]。
        """
        self._aggregates.append((kind, field, ops))

    def snapshot_every(self, ticks: int) -> None:
        """设置快照间隔。"""
        self._snapshot_interval = ticks

    def add_metric(self, name: str, fn: Callable[["WorldModel"], float]) -> None:
        """添加自定义指标函数。

        Args:
            name: 指标名（如 "entropy"）。
            fn: 接收 WorldModel 实例、返回 float 的函数。
        """
        self._metrics.append((name, fn))

    # ------------------------------------------------------------------
    # 内部：在每个 tick 后由 WorldModel.step() 调用
    # ------------------------------------------------------------------

    def _record_tick(self, model: "WorldModel", tick: int) -> None:
        """记录当前 tick 的数据。"""
        record: dict[str, Any] = {"tick": tick}

        # agent 级字段：每 kind 取活跃 entity 的值
        for kind, fields in self._agent_fields.items():
            lm = model._lifecycle.get(kind)
            if lm is None:
                continue
            active = lm.active_indices
            for f in fields:
                col = model._bridge.attr(kind, f)
                record[f"{kind}.{f}"] = col[active].copy() if len(active) > 0 else np.array([])

        # 聚合
        for kind, field, ops in self._aggregates:
            lm = model._lifecycle.get(kind)
            if lm is None:
                continue
            active = lm.active_indices
            if len(active) == 0:
                for op in ops:
                    record[f"{kind}.{field}.{op}"] = np.nan
                continue
            col = model._bridge.attr(kind, field)[active]
            for op in ops:
                key = f"{kind}.{field}.{op}"
                if op == "mean":
                    record[key] = float(np.mean(col))
                elif op == "std":
                    record[key] = float(np.std(col))
                elif op == "min":
                    record[key] = float(np.min(col))
                elif op == "max":
                    record[key] = float(np.max(col))
                elif op == "sum":
                    record[key] = float(np.sum(col))
                elif op == "count":
                    record[key] = len(active)

        # 自定义指标
        for name, fn in self._metrics:
            record[f"metric.{name}"] = fn(model)

        self._records.append(record)

    # ------------------------------------------------------------------
    # 导出 API
    # ------------------------------------------------------------------

    def export_dataframe(self):
        """导出为 pandas DataFrame。"""
        import pandas as pd
        return pd.DataFrame(self._records)

    def export_numpy(self) -> dict[str, np.ndarray]:
        """导出为 NumPy 数组字典。

        Returns:
            dict of field_name → 2D array (ticks × values)。
        """
        if not self._records:
            return {}
        result: dict[str, list] = {}
        for record in self._records:
            for key, val in record.items():
                if key not in result:
                    result[key] = []
                result[key].append(val)
        return {k: np.array(v) for k, v in result.items()}
