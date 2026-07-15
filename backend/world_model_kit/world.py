"""WorldModel —— 世界模型核心类。

WorldModel 是用户唯一需要直接实例化的类。它持有所有 EntityPool、
生命周期管理器、调度器、采集器，提供 L2 API 的全部入口。

内部数据流::

    User code (@step_for)
        ↓ 调用 L2 API (move, distance, spawn, kill...)
    WorldModel
        ↓ 翻译为 RECS 操作
    EntityPool (SoA) / Backend (NumPy / PyTorch / MLX / JAX)
        ↓ 向量化执行

Examples:
    >>> model = WorldModel(world_width=200, world_height=200)
    >>> prey = EntityKind("prey", position=True, energy=True)
    >>> model.register_kind(prey)
    >>> ids = model.spawn("prey", n=100, x=np.random.uniform(0,200,100),
    ...                    y=np.random.uniform(0,200,100), energy=50.0)
    >>> @model.step_for("prey")
    ... def prey_step(m, ids):
    ...     m.move(ids, np.random.uniform(-1,1,len(ids)),
    ...            np.random.uniform(-1,1,len(ids)))
    >>> model.step()
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np
from recs import EntityPool

from world_model_kit.entity_kind import EntityKind
from world_model_kit.entity_lifecycle import EntityLifecycleManager
from world_model_kit.entity_pool_bridge import EntityPoolBridge

logger = logging.getLogger(__name__)


class WorldModelError(Exception):
    """world-model-kit 通用异常。"""
    pass


class WorldModel:
    """世界模型核心类。

    持有所有 EntityPool、生命周期管理器、step 注册表。
    提供 L2 API 的全部入口。

    Attributes:
        world_width: 世界宽度。
        world_height: 世界高度。
        _bridge: EntityPoolBridge 实例。
        _lifecycle: kind_name → EntityLifecycleManager 映射。
        _step_registry: kind_name → (step_fn, step_fn_id) 映射。
        _step_order: kind 的 step 执行顺序。
        _tick: 当前 tick 计数。
    """

    def __init__(
        self,
        world_width: float = 100.0,
        world_height: float = 100.0,
        backend: str = "numpy",
        seed: int | None = None,
    ) -> None:
        """初始化世界模型。

        Args:
            world_width: 世界宽度（默认 100.0）。
            world_height: 世界高度（默认 100.0）。
            backend: RECS 计算后端（"numpy" / "torch" / "mlx" / "jax"）。
            seed: 随机种子（设为整数可复现仿真）。
        """
        self.world_width = world_width
        self.world_height = world_height

        self._bridge = EntityPoolBridge(backend=backend)
        self._lifecycle: dict[str, EntityLifecycleManager] = {}
        self._step_registry: dict[str, tuple[Callable, int]] = {}
        self._step_order: list[str] = []
        self._tick: int = 0

        if seed is not None:
            np.random.seed(seed)

        logger.info(
            "WorldModel 初始化: %sx%s, backend=%s, seed=%s",
            world_width, world_height, backend, seed,
        )

    # ==================================================================
    # EntityKind 注册
    # ==================================================================

    def register_kind(self, kind: EntityKind) -> None:
        """注册一个 Agent 类型。

        为每个 kind 创建一个独立 EntityPool 和 LifecycleManager。

        Args:
            kind: EntityKind 描述符。

        Raises:
            WorldModelError: 当 kind 已注册时。
        """
        if self._bridge.has_pool(kind.name):
            raise WorldModelError(
                f"EntityKind '{kind.name}' 已注册，不能重复注册。"
            )
        pool = self._bridge.create_pool(kind)
        self._lifecycle[kind.name] = EntityLifecycleManager(pool, kind.name)
        self._step_order.append(kind.name)
        logger.info("注册 EntityKind: %s", kind.name)

    def unregister_kind(self, name: str) -> None:
        """注销一个 Agent 类型。

        Args:
            name: kind 名称。
        """
        self._bridge.remove_pool(name)
        self._lifecycle.pop(name, None)
        self._step_registry.pop(name, None)
        if name in self._step_order:
            self._step_order.remove(name)
        logger.info("注销 EntityKind: %s", name)

    def list_kinds(self) -> list[str]:
        """列出所有已注册的 kind 名称。"""
        return self._bridge.list_kinds()

    # ==================================================================
    # Agent 生命周期 (L2)
    # ==================================================================

    def spawn(
        self, kind: str, n: int = 1, **attrs: object
    ) -> np.ndarray:
        """批量创建 Agent。

        新 Agent 处于 PENDING 状态，需要显式 activate() 才加入 step 循环。

        Args:
            kind: kind 名称。
            n: 创建数量。
            **attrs: 属性值（支持标量广播或与 n 等长数组）。

        Returns:
            np.ndarray: 新 Agent 的 pool 内部索引。

        Raises:
            KeyError: 当 kind 未注册时。
        """
        lm = self._lifecycle.get(kind)
        if lm is None:
            raise KeyError(
                f"EntityKind '{kind}' 未注册。请先调用 register_kind()。"
            )
        step_fn_id = -1
        if kind in self._step_registry:
            _, step_fn_id = self._step_registry[kind]
        indices = lm.spawn(n, step_fn_id=step_fn_id, **attrs)
        # spawn 后立即激活（默认行为——若需要延迟激活，用户可以 deactivate）
        lm.activate(indices)
        logger.debug("spawn %s: n=%d, indices=%s", kind, n, indices)
        return indices

    def activate(self, kind: str, ids: np.ndarray) -> None:
        """批量激活 Agent。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 的索引数组。
        """
        self._lifecycle[kind].activate(ids)

    def deactivate(self, kind: str, ids: np.ndarray) -> None:
        """批量停用 Agent。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 的索引数组。
        """
        self._lifecycle[kind].deactivate(ids)

    def kill(self, kind: str, ids: np.ndarray) -> None:
        """批量删除 Agent。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 的索引数组。
        """
        self._lifecycle[kind].kill(ids)

    def get_pool(self, kind: str) -> EntityPool:
        """获取 kind 对应的底层 EntityPool（L1 直通入口）。

        Args:
            kind: kind 名称。

        Returns:
            RECS EntityPool 实例。
        """
        return self._bridge.get_pool(kind)

    # ==================================================================
    # 便捷属性访问
    # ==================================================================

    @property
    def d(self) -> dict[str, dict[str, np.ndarray]]:
        """所有 kind 的属性列视图。

        Returns:
            嵌套字典: kind_name → {col_name → ndarray}
        """
        result: dict[str, dict[str, np.ndarray]] = {}
        for name in self._bridge.list_kinds():
            pool = self._bridge.get_pool(name)
            result[name] = pool.d
        return result

    def attr(self, kind: str, name: str) -> np.ndarray:
        """读取指定 kind 的属性列。

        Args:
            kind: kind 名称。
            name: 属性列名。

        Returns:
            属性列数据的视图。
        """
        return self._bridge.attr(kind, name)

    def set_attr(
        self,
        kind: str,
        name: str,
        indices: np.ndarray,
        values: Any,
    ) -> None:
        """按索引写入属性列。

        Args:
            kind: kind 名称。
            name: 属性列名。
            indices: 目标索引数组。
            values: 写入值（标量或数组）。
        """
        self._bridge.set_attr(kind, name, indices, values)

    # ==================================================================
    # 空间操作 (L2)
    # ==================================================================

    def move(
        self, kind: str, ids: np.ndarray, dx: Any, dy: Any
    ) -> None:
        """相对位移——向量化批量移动。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 索引（int 数组）。
            dx: x 方向位移（标量或与 ids 等长数组）。
            dy: y 方向位移（标量或与 ids 等长数组）。
        """
        if len(ids) == 0:
            return
        pool = self._bridge.get_pool(kind)
        pool.d["x"][ids] = pool.d["x"][ids] + np.asarray(dx, dtype=np.float32)
        pool.d["y"][ids] = pool.d["y"][ids] + np.asarray(dy, dtype=np.float32)

    def move_to(
        self, kind: str, ids: np.ndarray, target_x: Any, target_y: Any
    ) -> None:
        """绝对移动——向量化批量设置位置。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 索引。
            target_x: 目标 x 坐标（标量或数组）。
            target_y: 目标 y 坐标（标量或数组）。
        """
        pool = self._bridge.get_pool(kind)
        pool.d["x"][ids] = target_x
        pool.d["y"][ids] = target_y

    def move_toward(
        self,
        kind: str,
        ids: np.ndarray,
        target_x: float,
        target_y: float,
        max_distance: float,
    ) -> None:
        """朝向目标点移动（每步最多 max_distance）。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 索引。
            target_x: 目标 x 坐标。
            target_y: 目标 y 坐标。
            max_distance: 单步最大移动距离。
        """
        pool = self._bridge.get_pool(kind)
        x = pool.d["x"][ids]
        y = pool.d["y"][ids]
        dx = np.asarray(target_x) - x
        dy = np.asarray(target_y) - y
        dist = np.sqrt(dx * dx + dy * dy)
        # 避免除零：距离 < max_distance 的 agent 直接到达
        mask = dist > max_distance
        scale = np.where(mask, max_distance / np.maximum(dist, 1e-10), 1.0)
        pool.d["x"][ids] = x + dx * scale
        pool.d["y"][ids] = y + dy * scale

    def clamp_to_world(self, kind: str, ids: np.ndarray) -> None:
        """将 Agent 钳制在世界边界内。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 索引。
        """
        pool = self._bridge.get_pool(kind)
        np.clip(pool.d["x"][ids], 0, self.world_width, out=pool.d["x"][ids])
        np.clip(pool.d["y"][ids], 0, self.world_height, out=pool.d["y"][ids])

    def wrap_toroidal(self, kind: str, ids: np.ndarray) -> None:
        """环形世界——穿墙从对面出现。

        Args:
            kind: kind 名称。
            ids: 目标 Agent 索引。
        """
        pool = self._bridge.get_pool(kind)
        pool.d["x"][ids] = pool.d["x"][ids] % self.world_width
        pool.d["y"][ids] = pool.d["y"][ids] % self.world_height

    def distance(
        self, kind: str, a_ids: np.ndarray, b_ids: np.ndarray
    ) -> np.ndarray:
        """成对距离（a[i] 到 b[i]）。

        Args:
            kind: kind 名称。
            a_ids: 第一组 Agent 索引。
            b_ids: 第二组 Agent 索引（与 a_ids 等长）。

        Returns:
            np.ndarray: 成对距离数组。
        """
        pool = self._bridge.get_pool(kind)
        ax = pool.d["x"][a_ids]
        ay = pool.d["y"][a_ids]
        bx = pool.d["x"][b_ids]
        by = pool.d["y"][b_ids]
        return np.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

    def within_radius(
        self,
        kind: str,
        ids: np.ndarray,
        cx: Any,
        cy: Any,
        radius: float,
    ) -> np.ndarray:
        """半径内搜索——返回每个查询点半径内的所有 Agent。

        Args:
            kind: kind 名称。
            ids: 候选 Agent 的索引（在这些 Agent 中搜索）。
            cx: 查询中心 x 坐标（标量或数组）。
            cy: 查询中心 y 坐标（标量或数组）。
            radius: 搜索半径。

        Returns:
            np.ndarray: ids 中满足 distance < radius 的 Agent 索引。
        """
        pool = self._bridge.get_pool(kind)
        x = pool.d["x"][ids]
        y = pool.d["y"][ids]
        dx = x - np.asarray(cx)
        dy = y - np.asarray(cy)
        dist = np.sqrt(dx * dx + dy * dy)
        return ids[dist < radius]

    # ==================================================================
    # 调度 (L2)
    # ==================================================================

    @property
    def tick(self) -> int:
        """当前 tick 计数（从 1 开始）。"""
        return self._tick

    def step(self) -> None:
        """执行一个 tick。

        遍历 _step_order 中的所有 kind，对每个 kind 取 active_indices，
        调用注册的 step 函数。
        """
        self._tick += 1

        for kind in self._step_order:
            lm = self._lifecycle.get(kind)
            if lm is None:
                continue
            active_ids = lm.active_indices
            if len(active_ids) == 0:
                continue

            reg = self._step_registry.get(kind)
            if reg is not None:
                step_fn, _ = reg
                try:
                    step_fn(self, active_ids)
                except Exception:
                    logger.exception(
                        "step_for '%s' 在 tick %d 执行失败", kind, self._tick
                    )
                    raise

    def run(self, ticks: int) -> None:
        """运行指定 tick 数。

        Args:
            ticks: 要运行的 tick 数量。
        """
        for _ in range(ticks):
            self.step()

    def step_for(self, kind: str) -> Callable:
        """装饰器：注册指定 kind 的 step 函数。

        用法::

            @model.step_for("prey")
            def prey_step(m, ids):
                m.move("prey", ids, dx, dy)

        Args:
            kind: kind 名称。

        Returns:
            装饰器函数。
        """

        def decorator(fn: Callable) -> Callable:
            lm = self._lifecycle.get(kind)
            if lm is None:
                raise WorldModelError(
                    f"EntityKind '{kind}' 未注册。请先调用 register_kind()。"
                )
            fn_id = lm.register_step_fn()
            self._step_registry[kind] = (fn, fn_id)
            logger.info("注册 step_for: %s → %s", kind, fn.__name__)
            return fn

        return decorator
