"""WorldModel —— 世界模型核心类 v0.2.0。

WorldModel 是用户唯一需要直接实例化的类。它持有所有 EntityPool、
生命周期管理器、调度器、采集器，提供 L2 API 的全部入口。

v0.2.0 核心变更：geometry 驱动的嵌套 Entity 树 + tags + parent 坐标链。

内部数据流::

    User code (@step_for)
        ↓ 调用 L2 API (move, distance, spawn, kill...)
    WorldModel
        ↓ 翻译为 RECS 操作 + Geometry 分发
    EntityPool (SoA) / Backend (NumPy / PyTorch / MLX / JAX)
        ↓ 向量化执行

Examples:
    >>> model = WorldModel()
    >>> model.add_root_surface(200, 200)
    >>> prey = EntityKind("prey", geometry="point",
    ...                   tags={"energy": np.float32})
    >>> model.register_kind(prey)
    >>> ids = model.spawn("prey", n=100, u=np.random.uniform(0,200,100),
    ...                    v=np.random.uniform(0,200,100), energy=50.0)
    >>> @model.step_for("prey")
    ... def prey_step(m, ids):
    ...     angle = np.random.uniform(0, 2*np.pi, len(ids))
    ...     m.move("prey", ids, np.column_stack([np.cos(angle), np.sin(angle)]))
    >>> model.step()
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

import numpy as np
from recs import EntityPool

from world_model_kit.entity_kind import EntityKind
from world_model_kit.entity_lifecycle import EntityLifecycleManager
from world_model_kit.entity_pool_bridge import EntityPoolBridge
from world_model_kit.geometry.base import Geometry
from world_model_kit.geometry.point import PointGeometry
from world_model_kit.geometry.surface import SurfaceGeometry
from world_model_kit.geometry.volume import VolumeGeometry
from world_model_kit.perception import Perception
from world_model_kit.schedule.schedulers import SchedulerBase, SequentialScheduler

logger = logging.getLogger(__name__)


class WorldModelError(Exception):
    """world-model-kit 通用异常。"""
    pass


class WorldModel:
    """世界模型核心类 v0.2.0。

    持有所有 EntityPool、生命周期管理器、geometry、调度器、采集器。
    提供 L2 API 的全部入口。

    创建 2D 世界::

        model = WorldModel()
        model.add_root_surface(200, 200, boundary_u="clamp", boundary_v="clamp")

    Attributes:
        _bridge: EntityPoolBridge 实例。
        _lifecycle: kind_name → EntityLifecycleManager 映射。
        _step_registry: kind_name → (step_fn, step_fn_id) 映射。
        _step_order: kind 的 step 执行顺序。
        _tick: 当前 tick 计数。
        _kind_defs: kind_name → EntityKind 定义（用于 geometry 查找）。
        _tag_index: tag_name → set of kind_names（跨 kind 查询）。
        _geometry: kind_name → Geometry 实例。
        _root_geometry: 根 geometry（由 add_root_surface / add_root_volume 设置）。
        _scheduler: 调度器。
        _collector: DataCollector 实例（可选）。
        _resources: type → resource 的全局单例字典。
    """

    def __init__(
        self,
        backend: str = "numpy",
        seed: int | None = None,
        scheduler: SchedulerBase | None = None,
    ) -> None:
        """初始化世界模型。

        Args:
            backend: RECS 计算后端。
            seed: 随机种子。
            scheduler: 调度器（默认 SequentialScheduler）。
        """
        self._bridge = EntityPoolBridge(backend=backend)
        self._lifecycle: dict[str, EntityLifecycleManager] = {}
        self._step_registry: dict[str, tuple[Callable, int]] = {}
        self._step_order: list[str] = []
        self._tick: int = 0
        self._kind_defs: dict[str, EntityKind] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._geometry: dict[str, Geometry] = {}
        self._root_geometry: Geometry | None = None
        self._scheduler = scheduler or SequentialScheduler()
        self._resources: dict[type, Any] = {}
        self._collector = None

        if seed is not None:
            np.random.seed(seed)

        logger.info("WorldModel v0.2.0: backend=%s, seed=%s", backend, seed)

    # ==================================================================
    # 根 Geometry 设置
    # ==================================================================

    def add_root_surface(
        self,
        width: float,
        height: float,
        boundary_u: str = "clamp",
        boundary_v: str = "clamp",
    ) -> SurfaceGeometry:
        """添加 2D 矩形 surface 作为根 geometry。

        启用 clamp_to_world / wrap_toroidal 等边界操作。

        Args:
            width: U 方向范围 [0, width]。
            height: V 方向范围 [0, height]。
            boundary_u: U 方向边界模式 ("clamp" / "toroidal" / "bounce")。
            boundary_v: V 方向边界模式。

        Returns:
            创建的 SurfaceGeometry 实例。
        """
        geo = SurfaceGeometry(
            width=width, height=height,
            boundary_u=boundary_u, boundary_v=boundary_v,
        )
        self._root_geometry = geo
        logger.info("根 surface: %sx%s, boundary=(%s,%s)",
                     width, height, boundary_u, boundary_v)
        return geo

    def add_root_volume(
        self, width: float, height: float, depth: float,
    ) -> VolumeGeometry:
        """添加 3D 立方体作为根 geometry。

        Args:
            width: U 方向范围。
            height: V 方向范围。
            depth: W 方向范围。

        Returns:
            创建的 VolumeGeometry 实例。
        """
        geo = VolumeGeometry(width=width, height=height, depth=depth)
        self._root_geometry = geo
        logger.info("根 volume: %sx%sx%s", width, height, depth)
        return geo

    # ==================================================================
    # EntityKind 注册
    # ==================================================================

    def register_kind(self, kind: EntityKind) -> None:
        """注册一个 EntityKind。

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
        self._kind_defs[kind.name] = kind

        # 构建 tag 索引
        for tag_name in kind.tags:
            if tag_name not in self._tag_index:
                self._tag_index[tag_name] = set()
            self._tag_index[tag_name].add(kind.name)

        # 分配 geometry 实例
        if kind.geometry == "point":
            self._geometry[kind.name] = PointGeometry()
        elif kind.geometry == "surface":
            self._geometry[kind.name] = SurfaceGeometry()
        elif kind.geometry == "volume":
            self._geometry[kind.name] = VolumeGeometry()
        else:
            self._geometry[kind.name] = PointGeometry()

        logger.info("注册 EntityKind: %s (geometry=%s, dim=%.1f, tags=%s)",
                     kind.name, kind.geometry, kind.dim, list(kind.tags.keys()))

    def unregister_kind(self, name: str) -> None:
        """注销一个 EntityKind。"""
        self._bridge.remove_pool(name)
        self._lifecycle.pop(name, None)
        self._step_registry.pop(name, None)
        self._kind_defs.pop(name, None)
        self._geometry.pop(name, None)
        if name in self._step_order:
            self._step_order.remove(name)
        for tag_set in self._tag_index.values():
            tag_set.discard(name)
        logger.info("注销 EntityKind: %s", name)

    def list_kinds(self) -> list[str]:
        """列出所有已注册的 kind 名称。"""
        return self._bridge.list_kinds()

    # ==================================================================
    # Agent 生命周期 (L2)
    # ==================================================================

    def spawn(self, kind: str, n: int = 1, **attrs: object) -> np.ndarray:
        """批量创建 Agent。spawn 后立即激活。

        Args:
            kind: kind 名称。
            n: 创建数量。
            **attrs: 属性值。位置列使用 u/v（surface）或 u/v/w（volume）。

        Returns:
            np.ndarray: 新 Agent 的 pool 内部索引。
        """
        lm = self._lifecycle.get(kind)
        if lm is None:
            raise KeyError(f"EntityKind '{kind}' 未注册。")
        step_fn_id = -1
        if kind in self._step_registry:
            _, step_fn_id = self._step_registry[kind]
        indices = lm.spawn(n, step_fn_id=step_fn_id, **attrs)
        lm.activate(indices)
        pool = self._bridge.get_pool(kind)
        pool.d["_parent_id"][indices] = -1
        kd = self._kind_defs.get(kind)
        if kd is not None:
            pool.d["_type"][indices] = kd.type
        return indices

    def activate(self, kind: str, ids: np.ndarray) -> None:
        self._lifecycle[kind].activate(ids)

    def deactivate(self, kind: str, ids: np.ndarray) -> None:
        self._lifecycle[kind].deactivate(ids)

    def kill(self, kind: str, ids: np.ndarray) -> None:
        self._lifecycle[kind].kill(ids)

    def get_pool(self, kind: str) -> EntityPool:
        """L1 直通入口。"""
        return self._bridge.get_pool(kind)

    # ==================================================================
    # 属性访问
    # ==================================================================

    @property
    def d(self) -> dict[str, dict[str, np.ndarray]]:
        result: dict[str, dict[str, np.ndarray]] = {}
        for name in self._bridge.list_kinds():
            result[name] = self._bridge.get_pool(name).d
        return result

    def attr(self, kind: str, name: str) -> np.ndarray:
        """读取属性列。"""
        return self._bridge.attr(kind, name)

    def set_attr(self, kind: str, name: str, indices: np.ndarray, values: Any) -> None:
        self._bridge.set_attr(kind, name, indices, values)

    # ==================================================================
    # 空间操作 (v0.2.0 geometry-driven)
    # ==================================================================

    def move(
        self,
        kind: str,
        ids: np.ndarray,
        delta: np.ndarray,
        dt: float = 1.0,
    ) -> None:
        """相对位移 —— 向量化批量移动。

        delta.shape = (n, parent_dim)。对不同 geometry 自动分发。

        Args:
            kind: kind 名称。
            ids: 目标 entity 索引。
            delta: 位移向量，(n, 2) 用于 surface，(n, 3) 用于 volume。
            dt: 时间步长。
        """
        if len(ids) == 0:
            return
        pool = self._bridge.get_pool(kind)

        d = np.atleast_2d(np.asarray(delta, dtype=np.float32))
        if d.shape[0] == 1 and len(ids) > 1:
            d = np.tile(d, (len(ids), 1))

        if "u" not in pool.d:
            return

        pos = np.column_stack([pool.d["u"][ids], pool.d["v"][ids]])
        if "w" in pool.d:
            pos = np.column_stack([pos, pool.d["w"][ids]])

        geo = self._geometry.get(kind, PointGeometry())
        new_pos = geo.move(pos, d[:, :pos.shape[1]], dt)

        pool.d["u"][ids] = new_pos[:, 0]
        if new_pos.shape[1] >= 2 and "v" in pool.d:
            pool.d["v"][ids] = new_pos[:, 1]
        if new_pos.shape[1] >= 3 and "w" in pool.d:
            pool.d["w"][ids] = new_pos[:, 2]

    def move_to(self, kind: str, ids: np.ndarray, u: Any, v: Any) -> None:
        """绝对移动——批量设置参数坐标。"""
        pool = self._bridge.get_pool(kind)
        if "u" in pool.d:
            pool.d["u"][ids] = np.asarray(u, dtype=np.float32)
        if "v" in pool.d:
            pool.d["v"][ids] = np.asarray(v, dtype=np.float32)

    def move_toward(
        self, kind: str, ids: np.ndarray,
        target_u: float, target_v: float, max_distance: float,
    ) -> None:
        """朝向目标点移动。"""
        pool = self._bridge.get_pool(kind)
        u = pool.d["u"][ids].astype(np.float64)
        v = pool.d["v"][ids].astype(np.float64)
        du = np.float64(target_u) - u
        dv = np.float64(target_v) - v
        dist = np.sqrt(du * du + dv * dv)
        mask = dist > max_distance
        scale = np.where(mask, max_distance / np.maximum(dist, 1e-10), 1.0)
        pool.d["u"][ids] = (u + du * scale).astype(np.float32)
        pool.d["v"][ids] = (v + dv * scale).astype(np.float32)

    def clamp_to_world(self, kind: str, ids: np.ndarray) -> None:
        """钳制到根 surface 边界内。需先调用 add_root_surface()。"""
        if self._root_geometry is None:
            return
        pool = self._bridge.get_pool(kind)
        if "u" not in pool.d:
            return
        pos = np.column_stack([pool.d["u"][ids], pool.d["v"][ids]])
        if isinstance(self._root_geometry, SurfaceGeometry):
            new_pos = self._root_geometry.clamp(pos)
            pool.d["u"][ids] = new_pos[:, 0]
            pool.d["v"][ids] = new_pos[:, 1]

    def wrap_toroidal(self, kind: str, ids: np.ndarray) -> None:
        """环形环绕根 surface 边界。需先调用 add_root_surface()。"""
        if self._root_geometry is None:
            return
        pool = self._bridge.get_pool(kind)
        if "u" not in pool.d:
            return
        pos = np.column_stack([pool.d["u"][ids], pool.d["v"][ids]])
        if isinstance(self._root_geometry, SurfaceGeometry):
            new_pos = self._root_geometry.wrap_toroidal(pos)
            pool.d["u"][ids] = new_pos[:, 0]
            pool.d["v"][ids] = new_pos[:, 1]

    def distance(self, kind: str, a_ids: np.ndarray, b_ids: np.ndarray) -> np.ndarray:
        """成对距离。"""
        pool = self._bridge.get_pool(kind)
        au = pool.d["u"][a_ids].astype(np.float64)
        av = pool.d["v"][a_ids].astype(np.float64)
        bu = pool.d["u"][b_ids].astype(np.float64)
        bv = pool.d["v"][b_ids].astype(np.float64)
        return np.sqrt((au - bu) ** 2 + (av - bv) ** 2)

    def within_radius(
        self, kind: str, ids: np.ndarray,
        cx: Any, cy: Any, radius: float,
    ) -> np.ndarray:
        """半径内搜索。"""
        pool = self._bridge.get_pool(kind)
        u = pool.d["u"][ids].astype(np.float64)
        v = pool.d["v"][ids].astype(np.float64)
        du = u - np.float64(cx)
        dv = v - np.float64(cy)
        dist = np.sqrt(du * du + dv * dv)
        return ids[dist < radius]

    def resolve_world_position(self, kind: str, ids: np.ndarray) -> np.ndarray:
        """递归求解世界坐标。返回 shape=(n, 3)。"""
        pool = self._bridge.get_pool(kind)
        if "u" not in pool.d:
            return np.zeros((len(ids), 3), dtype=np.float32)
        pos = np.column_stack([pool.d["u"][ids], pool.d["v"][ids]])
        if "w" in pool.d:
            pos = np.column_stack([pos, pool.d["w"][ids]])
        geo = self._geometry.get(kind, PointGeometry())
        return geo.param_to_local(pos)

    # ==================================================================
    # 嵌入与交互
    # ==================================================================

    def embed_to(self, kind: str, ids: np.ndarray,
                 parent_kind: str, parent_ids: np.ndarray,
                 method: str = "nearest") -> None:
        """将 entity 挂载到新的 parent entity。"""
        if len(ids) == 0:
            return
        child_pool = self._bridge.get_pool(kind)
        parent_pool = self._bridge.get_pool(parent_kind)
        for i, child_id in enumerate(ids):
            child_pool.d["_parent_id"][child_id] = int(parent_ids[i])

    def detach(self, kind: str, ids: np.ndarray) -> None:
        """脱离当前 parent，回到 root。"""
        if len(ids) == 0:
            return
        self._bridge.get_pool(kind).d["_parent_id"][ids] = -1

    def reattach(self, kind: str, ids: np.ndarray,
                 new_parent_kind: str, new_parent_ids: np.ndarray,
                 method: str = "nearest") -> None:
        """重新挂载到新 parent。"""
        self.detach(kind, ids)
        self.embed_to(kind, ids, new_parent_kind, new_parent_ids, method)

    def intersects(self, kind_a: str, id_a: int,
                   kind_b: str, id_b: int) -> bool:
        """检查两个 entity 是否相交。当前仅支持 Point-Surface。"""
        pool_a = self._bridge.get_pool(kind_a)
        pool_b = self._bridge.get_pool(kind_b)
        geo_b = self._geometry.get(kind_b, PointGeometry())
        pos_a = np.array([[pool_a.d["u"][id_a], pool_a.d["v"][id_a]]])
        return bool(geo_b.contains(pos_a)[0])

    def intersecting_pairs(self, kind_a: str, kind_b: str) -> list[tuple[int, int]]:
        """返回所有相交的 entity 对。"""
        result: list[tuple[int, int]] = []
        lm_a = self._lifecycle.get(kind_a)
        lm_b = self._lifecycle.get(kind_b)
        if lm_a is None or lm_b is None:
            return result
        for a_id in lm_a.active_indices:
            for b_id in lm_b.active_indices:
                if self.intersects(kind_a, int(a_id), kind_b, int(b_id)):
                    result.append((int(a_id), int(b_id)))
        return result

    # ==================================================================
    # Tag 系统与跨 kind 查询
    # ==================================================================

    def tagged(self, tag_name: str) -> dict[str, np.ndarray]:
        """返回所有定义了该 tag 的 kind 的活跃 entity 索引。

        Returns:
            {kind_name: active_indices}
        """
        result: dict[str, np.ndarray] = {}
        for kind_name in self._tag_index.get(tag_name, set()):
            lm = self._lifecycle.get(kind_name)
            if lm is not None and lm.active_count > 0:
                result[kind_name] = lm.active_indices
        return result

    def kinds_with_tag(self, tag_name: str) -> list[str]:
        """返回所有定义了该 tag 的 kind 名称列表。"""
        return sorted(self._tag_index.get(tag_name, set()))

    def where(self, kind: str, tag_name: str, *,
              lt: float | None = None,
              gt: float | None = None,
              eq: Any = None) -> np.ndarray:
        """按 tag 值过滤 entity 索引。"""
        pool = self._bridge.get_pool(kind)
        if tag_name not in pool.d:
            return np.array([], dtype=np.int64)
        col = pool.d[tag_name]
        lm = self._lifecycle[kind]
        active = lm.active_indices
        vals = col[active]
        mask = np.ones(len(active), dtype=bool)
        if lt is not None:
            mask &= vals < lt
        if gt is not None:
            mask &= vals > gt
        if eq is not None:
            mask &= vals == eq
        return active[mask]

    # ==================================================================
    # 调度
    # ==================================================================

    @property
    def tick(self) -> int:
        return self._tick

    def step(self) -> None:
        """执行一个 tick。

        1. 按 scheduler 排序 kind 和 entity
        2. 对每个 entity 填充 Perception（如果声明了 perceive）
        3. 调用 step 函数
        4. 触发 DataCollector
        """
        self._tick += 1
        kind_order = self._scheduler.get_step_order(self)

        for kind in kind_order:
            lm = self._lifecycle.get(kind)
            if lm is None:
                continue
            active_ids = lm.active_indices
            if len(active_ids) == 0:
                continue

            reg = self._step_registry.get(kind)
            if reg is None:
                continue

            step_fn, _ = reg
            kd = self._kind_defs.get(kind)

            # 感知填充
            if kd is not None and kd.perceive is not None:
                perception = self._prepare_perception(kind, active_ids, kd.perceive)
                try:
                    step_fn(self, perception)
                except Exception:
                    logger.exception("step_for '%s' 在 tick %d 失败", kind, self._tick)
                    raise
            else:
                try:
                    step_fn(self, active_ids)
                except Exception:
                    logger.exception("step_for '%s' 在 tick %d 失败", kind, self._tick)
                    raise

        # 触发采集器
        if self._collector is not None:
            self._collector._record_tick(self, self._tick)

    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.step()

    def step_for(self, kind: str) -> Callable:
        """装饰器：注册指定 kind 的 step 函数。"""

        def decorator(fn: Callable) -> Callable:
            lm = self._lifecycle.get(kind)
            if lm is None:
                raise WorldModelError(f"EntityKind '{kind}' 未注册。")
            fn_id = lm.register_step_fn()
            self._step_registry[kind] = (fn, fn_id)
            logger.info("注册 step_for: %s → %s", kind, fn.__name__)
            return fn

        return decorator

    # ==================================================================
    # Perception 感知框架
    # ==================================================================

    def _prepare_perception(
        self, kind: str, active_ids: np.ndarray, perceive_spec: dict,
    ) -> Perception:
        """为指定 kind 的活跃 entity 填充 Perception。"""
        perception = Perception()

        # self_tags
        if "self_tags" in perceive_spec:
            tag_names = perceive_spec["self_tags"]
            if tag_names is None:
                kd = self._kind_defs.get(kind)
                tag_names = list(kd.tags.keys()) if kd else []
            for tag in tag_names:
                col = self._bridge.attr(kind, tag)
                perception.self_tags[tag] = col[active_ids]

        # neighbors
        of_kinds = perceive_spec.get("of_kinds", [])
        radius = perceive_spec.get("radius", 0.0)
        if of_kinds and radius > 0:
            pool = self._bridge.get_pool(kind)
            qu = pool.d["u"][active_ids]
            qv = pool.d["v"][active_ids]
            for target_kind in of_kinds:
                t_lm = self._lifecycle.get(target_kind)
                if t_lm is None:
                    continue
                t_ids = t_lm.active_indices
                if len(t_ids) == 0:
                    perception.neighbors[target_kind] = np.array([], dtype=np.int64)
                    continue
                t_pool = self._bridge.get_pool(target_kind)
                tu = t_pool.d["u"][t_ids]
                tv = t_pool.d["v"][t_ids]
                neighbors_list = []
                for i in range(len(active_ids)):
                    du = tu - qu[i]
                    dv = tv - qv[i]
                    dist = np.sqrt(du * du + dv * dv)
                    neighbors_list.append(t_ids[dist < radius])
                perception.neighbors[target_kind] = np.array(
                    [arr for arr in neighbors_list], dtype=object
                )

        # collisions
        collision_radius = perceive_spec.get("collision_radius", 0.0)
        if collision_radius > 0:
            perception.collisions = {}  # 同 neighbors 逻辑，radius = collision_radius

        return perception

    # ==================================================================
    # Plugin + Resource 系统
    # ==================================================================

    @property
    def behaviors(self):
        """内置行为注册表。"""
        from world_model_kit.behaviors.registry import BehaviorRegistry
        return BehaviorRegistry(self)

    @property
    def collector(self):
        """DataCollector 实例（延迟初始化）。"""
        if self._collector is None:
            from world_model_kit.collect.collector import DataCollector
            self._collector = DataCollector()
        return self._collector

    def add_plugin(self, plugin) -> None:
        """注册一个 WorldPlugin。"""
        plugin.build(self)
        logger.info("加载插件: %s", plugin.name)

    def add_resource(self, resource: Any) -> None:
        """注入全局单例资源。用 type(resource) 作为 key。"""
        self._resources[type(resource)] = resource

    def get_resource(self, resource_type: type) -> Any:
        """获取全局资源。"""
        return self._resources.get(resource_type)

    # ==================================================================
    # ViewModel 导出
    # ==================================================================

    def export_viewmodel(self, format: str = "json",
                         viewport: dict | None = None) -> bytes | dict:
        """导出当前 tick 的 WorldViewModel。"""
        from world_model_kit.viewmodel.export import export_viewmodel
        return export_viewmodel(self, format=format, viewport=viewport)

    def export_dataframe(self):
        """导出 DataCollector 记录为 DataFrame。"""
        if self._collector is None:
            raise WorldModelError("未配置 DataCollector。使用 model.collector.collect(...) 配置。")
        return self._collector.export_dataframe()
