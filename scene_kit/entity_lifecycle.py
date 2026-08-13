"""EntityLifecycleManager —— 实体生命周期管理器。

管理一个 kind 下所有实体的状态转换。核心操作全部向量化——
通过布尔掩码在 SoA 列上批量执行。

状态机::

    PENDING ──activate()──► ACTIVE ◄──deactivate()──► DORMANT
                               │                          │
                               └────kill()──► DEAD ◄──────┘

状态存储在 EntityPool 的系统保留列中：
- _active 列：bool，True = 处于 ACTIVE 状态
- _step_fn 列：int32，已注册的 step 函数 ID（-1 = 未注册）
"""

from __future__ import annotations

import numpy as np
from recs import EntityPool


class EntityLifecycleManager:
    """管理一个 kind 下所有实体的生命周期。

    核心操作全部向量化——通过布尔掩码在 SoA 列上批量执行。
    每个 kind 对应一个 LifecycleManager 实例。

    Attributes:
        pool: 关联的 RECS EntityPool。
        kind_name: kind 名称。
        _next_step_fn_id: 下一个可分配的 step 函数 ID。
    """

    def __init__(self, pool: EntityPool, kind_name: str) -> None:
        """初始化生命周期管理器。

        Args:
            pool: 已创建的 RECS EntityPool 实例。
            kind_name: kind 名称。
        """
        self.pool = pool
        self.kind_name = kind_name
        self._next_step_fn_id = 0

    # ------------------------------------------------------------------
    # 状态查询（向量化）
    # ------------------------------------------------------------------

    @property
    def active_mask(self) -> np.ndarray:
        """返回当前激活实体的布尔掩码。

        Returns:
            bool 数组，长度 = pool.size。True 表示 ACTIVE。
        """
        # RECS 的 ``o`` 列是底层唯一的启用真值。``_active`` 仅作为
        # v0.2 兼容列保留，所有生命周期写操作会同时更新两者。
        raw = self.pool.d["o"][: self.pool.size]
        try:
            return np.asarray(self.pool.backend.to_numpy(raw), dtype=bool)
        except Exception:
            return np.asarray(raw, dtype=bool)

    @property
    def active_indices(self) -> np.ndarray:
        """返回当前激活实体的索引数组。

        Returns:
            int 数组，包含所有 _active == True 的索引。
            永远返回一维数组（即使只有一个活跃实体）。
        """
        mask = self.active_mask
        result = self.pool.backend.nonzero(mask)
        # 不同后端 nonzero 返回值不同：NumPy 返回 tuple，MLX 返回 array
        if isinstance(result, tuple):
            result = result[0]
        return np.atleast_1d(np.asarray(result, dtype=np.int64))

    @property
    def active_count(self) -> int:
        """返回当前激活实体数量。"""
        return int(self.active_mask.sum())

    # ------------------------------------------------------------------
    # 生命周期操作
    # ------------------------------------------------------------------

    def spawn(
        self, n: int = 1, *, step_fn_id: int = -1, **attrs: object
    ) -> np.ndarray:
        """批量创建实体并设置为 PENDING 状态。

        PENDING 表示实体已创建但尚未加入 step 循环。
        需要显式调用 activate() 将其提升为 ACTIVE。

        Args:
            n: 创建数量。
            step_fn_id: step 函数注册号（默认 -1 表示未注册）。
            **attrs: 属性值，支持标量广播。

        Returns:
            np.ndarray: 新创建实体的 pool 内部索引数组。
        """
        indices = self.pool.add(n, **attrs)
        # 设置系统保留列
        self.pool.d["_kind"][indices] = self.kind_name
        self.pool.d["_active"][indices] = False  # PENDING
        self.pool.d["o"][indices] = False
        self.pool.d["_step_fn"][indices] = step_fn_id
        return indices

    def activate(self, indices: np.ndarray) -> None:
        """批量激活实体（PENDING → ACTIVE 或 DORMANT → ACTIVE）。

        只操作 _active 列的一个切片，O(len(indices))。

        Args:
            indices: 目标实体的索引数组。
        """
        if len(indices) == 0:
            return
        self.pool.d["_active"][indices] = True
        self.pool.enable(indices)

    def deactivate(self, indices: np.ndarray) -> None:
        """批量停用实体（ACTIVE → DORMANT）。

        实体保留在 pool 中但不参与 step 循环。可以重新 activate()。

        Args:
            indices: 目标实体的索引数组。
        """
        if len(indices) == 0:
            return
        self.pool.d["_active"][indices] = False
        self.pool.remove(indices)

    def kill(self, indices: np.ndarray) -> None:
        """永久删除实体（任意状态 → DEAD）。

        标记 _active=False。被删除的 slot 可在后续 spawn 中复用。

        Args:
            indices: 目标实体的索引数组。
        """
        if len(indices) == 0:
            return
        self.pool.d["_active"][indices] = False
        self.pool.remove(indices)
        self.pool.d["_step_fn"][indices] = -1

    # ------------------------------------------------------------------
    # Step 函数注册
    # ------------------------------------------------------------------

    def register_step_fn(self) -> int:
        """分配一个新的 step 函数 ID。

        Returns:
            int: 新分配的 step 函数 ID。
        """
        fid = self._next_step_fn_id
        self._next_step_fn_id += 1
        return fid
