"""EntityPoolBridge —— world-model-kit ↔ RECS EntityPool 的薄桥接层。

职责：
1. 管理每个 kind 的 EntityPool 实例
2. 提供 world-model-kit 风格的属性读写
3. 处理 dtype 映射与广播
4. 将 L2 API 调用翻译为 RECS 原语操作

设计原则：桥接层本身不包含业务逻辑——只是将 world-model-kit 语义
翻译为 RECS 的 EntityPool API 调用。
"""

from __future__ import annotations

from typing import Any

import numpy as np
from recs import EntityPool

from world_model_kit.entity_kind import EntityKind, _kind_to_dtypes


# 默认 EntityPool 初始容量
DEFAULT_CAPACITY = 1024


class EntityPoolBridge:
    """world-model-kit ↔ RECS EntityPool 桥接层。

    管理所有 kind 对应的 EntityPool 实例，提供统一的创建、读写接口。

    Attributes:
        _backend_name: RECS 后端名称（"numpy" / "torch" / "mlx" / "jax"）。
        _pools: kind_name → EntityPool 的映射字典。
    """

    def __init__(self, backend: str = "numpy") -> None:
        """初始化桥接层。

        Args:
            backend: RECS 计算后端名称。默认为 "numpy"。
        """
        self._backend_name = backend
        self._pools: dict[str, EntityPool] = {}

    # ------------------------------------------------------------------
    # Pool 生命周期
    # ------------------------------------------------------------------

    def create_pool(
        self, kind: EntityKind, capacity: int = DEFAULT_CAPACITY
    ) -> EntityPool:
        """为指定 kind 创建一个 RECS EntityPool。

        如果同名 kind 已存在，抛出 ValueError。

        Args:
            kind: EntityKind 描述符。
            capacity: 初始容量（默认 1024）。

        Returns:
            新创建的 EntityPool 实例。

        Raises:
            ValueError: 当 kind.name 已注册时。
        """
        if kind.name in self._pools:
            raise ValueError(
                f"EntityKind '{kind.name}' 已注册，不能重复创建。"
            )
        dtypes = _kind_to_dtypes(kind)
        pool = EntityPool(
            capacity=capacity,
            attr_dtypes=dtypes,
            backend=self._backend_name,
        )
        self._pools[kind.name] = pool
        return pool

    def has_pool(self, kind: str) -> bool:
        """检查指定 kind 的 EntityPool 是否存在。"""
        return kind in self._pools

    def get_pool(self, kind: str) -> EntityPool:
        """获取 kind 对应的 EntityPool 实例（L1 直通入口）。

        Args:
            kind: kind 名称。

        Returns:
            EntityPool 实例。

        Raises:
            KeyError: 当 kind 未注册时。
        """
        if kind not in self._pools:
            raise KeyError(
                f"EntityKind '{kind}' 未注册。请先调用 register_kind()。"
            )
        return self._pools[kind]

    def remove_pool(self, kind: str) -> None:
        """移除指定 kind 的 EntityPool。

        Args:
            kind: kind 名称。

        Raises:
            KeyError: 当 kind 未注册时。
        """
        if kind not in self._pools:
            raise KeyError(
                f"EntityKind '{kind}' 未注册，无法移除。"
            )
        del self._pools[kind]

    def list_kinds(self) -> list[str]:
        """列出所有已注册的 kind 名称。"""
        return list(self._pools.keys())

    # ------------------------------------------------------------------
    # 属性读写
    # ------------------------------------------------------------------

    def attr(
        self, kind: str, name: str, indices: np.ndarray | None = None
    ) -> np.ndarray:
        """读取属性列。

        Args:
            kind: kind 名称。
            name: 属性名（列名）。
            indices: 可选索引数组。为 None 时返回整列。

        Returns:
            属性列数据的视图或拷贝。
        """
        pool = self.get_pool(kind)
        col = pool.get_attr(name)
        if indices is not None:
            return col[indices]
        return col

    def set_attr(
        self,
        kind: str,
        name: str,
        indices: np.ndarray,
        values: Any,
    ) -> None:
        """按索引写入属性列。

        支持标量广播或与 indices 等长的一维数组。

        Args:
            kind: kind 名称。
            name: 属性名（列名）。
            indices: 目标索引数组。
            values: 写入值（标量或数组）。
        """
        pool = self.get_pool(kind)
        pool.set_attr(name, indices, values)

    def assign(
        self,
        kind: str,
        indices: np.ndarray,
        values_by_attr: dict[str, Any],
    ) -> None:
        """在同一索引上对多列批量赋值。

        Args:
            kind: kind 名称。
            indices: 目标索引数组。
            values_by_attr: 列名 → 值的字典。
        """
        pool = self.get_pool(kind)
        pool.assign(indices, values_by_attr)

    # ------------------------------------------------------------------
    # 便捷属性访问（常用列的简写）
    # ------------------------------------------------------------------

    @property
    def u_pos(self) -> dict[str, np.ndarray]:
        """所有 kind 的 u 列视图字典。"""
        return {k: p.get_attr("u") for k, p in self._pools.items() if "u" in p.d}

    @property
    def v_pos(self) -> dict[str, np.ndarray]:
        """所有 kind 的 v 列视图字典。"""
        return {k: p.get_attr("v") for k, p in self._pools.items() if "v" in p.d}
