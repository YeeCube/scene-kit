# world-model-kit API 手册

> **版本**: 0.2.0 | **最后更新**: 2026-07-23

---

## WorldModel

```python
from world_model_kit import WorldModel

model = WorldModel(
    backend: str = "numpy",           # "numpy" | "torch" | "mlx" | "jax"
    seed: int | None = None,
    scheduler: SchedulerBase | None = None,
)
```

### 根 Geometry

| 方法 | 说明 |
|---|---|
| `add_root_surface(width, height, boundary_u="clamp", boundary_v="clamp")` | 设置 2D surface 根 |
| `add_root_volume(width, height, depth)` | 设置 3D volume 根 |

### EntityKind 管理

| 方法 | 说明 |
|---|---|
| `register_kind(kind: EntityKind)` | 注册类型 |
| `unregister_kind(name: str)` | 注销类型 |
| `list_kinds() -> list[str]` | 列出所有已注册 kind |

### 生命周期

| 方法 | 签名 | 说明 |
|---|---|---|
| `spawn` | `(kind, n=1, **attrs) -> np.ndarray` | 批量创建 + 自动激活。位置列用 `u=`/`v=`（或 `w=`） |
| `activate` | `(kind, ids)` | 激活 |
| `deactivate` | `(kind, ids)` | 停用 |
| `kill` | `(kind, ids)` | 永久删除 |
| `get_pool` | `(kind) -> EntityPool` | L1 直通，返回 RECS EntityPool |

### 属性访问

| 方法 | 签名 | 说明 |
|---|---|---|
| `attr` | `(kind, name) -> np.ndarray` | 读列 |
| `set_attr` | `(kind, name, indices, values)` | 按索引写列 |

### 空间操作

| 方法 | 签名 | 说明 |
|---|---|---|
| `move` | `(kind, ids, delta: np.ndarray, dt=1.0)` | 向量化移动。`delta.shape = (n, parent_dim)` |
| `move_to` | `(kind, ids, u, v)` | 绝对设置参数坐标 |
| `move_toward` | `(kind, ids, target_u, target_v, max_distance)` | 朝向目标移动 |
| `clamp_to_world` | `(kind, ids)` | 钳制到根 surface 边界（需先 `add_root_surface`） |
| `wrap_toroidal` | `(kind, ids)` | 环形环绕 |
| `distance` | `(kind, a_ids, b_ids) -> np.ndarray` | 成对距离 |
| `within_radius` | `(kind, ids, cx, cy, radius) -> np.ndarray` | 半径搜索 |
| `resolve_world_position` | `(kind, ids) -> np.ndarray` | 递归求解世界坐标 → `(n, 3)` |

### 嵌入与交互

| 方法 | 签名 | 说明 |
|---|---|---|
| `embed_to` | `(kind, ids, parent_kind, parent_ids, method="nearest")` | 挂载到指定 parent entity |
| `detach` | `(kind, ids)` | 脱离 parent，回到根 |
| `reattach` | `(kind, ids, new_parent_kind, new_parent_ids)` | 切换宿主 |
| `intersects` | `(kind_a, id_a, kind_b, id_b) -> bool` | 两个 entity 是否相交 |
| `intersecting_pairs` | `(kind_a, kind_b) -> list[tuple]` | 返回所有相交对 |

### Tag 系统

| 方法 | 签名 | 说明 |
|---|---|---|
| `tagged` | `(tag_name) -> dict[str, np.ndarray]` | 返回所有有该 tag 的 kind → active_indices |
| `kinds_with_tag` | `(tag_name) -> list[str]` | 返回有该 tag 的 kind 名列表 |
| `where` | `(kind, tag_name, *, lt, gt, eq) -> np.ndarray` | 按 tag 值过滤 entity 索引 |

### 调度

| 属性/方法 | 说明 |
|---|---|
| `tick: int` | 当前 tick |
| `step()` | 执行一个 tick |
| `run(ticks: int)` | 运行指定 tick 数 |
| `step_for(kind)` | 装饰器，注册 step 函数 |

### Plugin & Resource

| 方法 | 签名 | 说明 |
|---|---|---|
| `add_plugin` | `(plugin: WorldPlugin)` | 注册插件 |
| `add_resource` | `(resource: Any)` | 注入全局资源（key = type(resource)） |
| `get_resource` | `(resource_type: type) -> Any` | 获取全局资源 |
| `behaviors` | 属性 → BehaviorRegistry | 内置行为注册表 |
| `collector` | 属性 → DataCollector | 数据采集器（延迟初始化） |

### ViewModel 导出

| 方法 | 签名 | 说明 |
|---|---|---|
| `export_viewmodel` | `(format="json", viewport=None) -> bytes \| dict` | 导出当前 tick 快照 |
| `export_dataframe` | `() -> pd.DataFrame` | 导出 DataCollector 记录 |

---

## EntityKind

```python
from world_model_kit import EntityKind

EntityKind(
    name: str,                      # 类型名（必须）
    geometry: str = "point",        # point | surface | volume | path | segment | hypergraph
    dim: float = 0.0,               # 内在维度（0=自动推断）
    parent: str | None = None,      # 父 kind 名称
    tags: dict[str, Any] = {},      # 领域属性字典
    type: str = "AGENT",            # AGENT | ENTITY | OBJECT | ENV
    perceive: dict | None = None,   # 感知声明
)
```

---

## Geometry（基类）

```python
from world_model_kit.geometry import Geometry

class Geometry(ABC):
    dim: float

    @abstractmethod
    def metric(self, p: np.ndarray, q: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def move(self, positions: np.ndarray, delta: np.ndarray, dt=1.0) -> np.ndarray: ...
    @abstractmethod
    def neighborhood(self, positions, query_points, radius) -> list[np.ndarray]: ...
    @abstractmethod
    def contains(self, positions: np.ndarray) -> np.ndarray: ...
    @abstractmethod
    def param_to_local(self, positions: np.ndarray) -> np.ndarray: ...
```

### 具体实现

| 类 | 说明 |
|---|---|
| `PointGeometry` | 0 维质点 |
| `SurfaceGeometry(width, height, boundary_u, boundary_v)` | 2D 矩形面 |
| `VolumeGeometry(width, height, depth)` | 3D 立方体 |

---

## Perception

```python
@dataclass
class Perception:
    self_tags: dict[str, np.ndarray]       # 自身 tags 值
    neighbors: dict[str, np.ndarray]       # target_kind → 邻域 entity 索引
    fields: dict[str, np.ndarray]          # 场名 → 位置场值（远期）
    collisions: dict[str, np.ndarray]      # 碰撞 entity 索引
```

---

## WorldPlugin

```python
class WorldPlugin(ABC):
    name: str

    def build(self, world: WorldModel):
        self.register_kinds(world)
        self.register_behaviors(world)
        self.register_collectors(world)
        self.register_resources(world)

    def register_kinds(self, world): ...
    def register_behaviors(self, world): ...
    def register_collectors(self, world): ...
    def register_resources(self, world): ...
```

---

## BehaviorRegistry

通过 `model.behaviors` 访问。

| 方法 | 签名 |
|---|---|
| `random_walk` | `(kind, step_size=1.0)` |
| `flocking` | `(kind, separation=1.5, alignment=1.0, cohesion=1.0, radius=5.0, max_speed=2.0)` |
| `pursuit_evasion` | `(pursuer_kind, evader_kind, capture_radius=2.0, pursuit_speed=1.5)` |

---

## Scheduler

```python
from world_model_kit.schedule import (
    SchedulerBase,         # 抽象基类
    SequentialScheduler,   # 创建顺序（默认）
    RandomScheduler,       # 每 tick 随机 shuffle
    ByKindScheduler,       # kind 分组内 shuffle
    PhaseScheduler,        # 阶段机
)
```

---

## DataCollector

通过 `model.collector` 访问。

| 方法 | 签名 | 说明 |
|---|---|---|
| `collect` | `(kind, fields: list[str])` | 记录 agent 级字段 |
| `aggregate` | `(kind, field, ops: list[str])` | 记录 population 级聚合。ops: mean/std/min/max/sum/count |
| `add_metric` | `(name, fn: Callable[[WorldModel], float])` | 自定义指标 |
| `export_dataframe` | `() -> pd.DataFrame` | 导出为 DataFrame |
| `export_numpy` | `() -> dict` | 导出为 NumPy 数组字典 |

---

## ViewModel 导出

```python
@dataclass
class AgentViewModel:
    id: int; kind: str
    position: list[float]   # [u, v] 或 [u, v, w]
    r: int; g: int; b: int; a: int
    size: float; heading: float | None

@dataclass
class WorldViewModel:
    tick: int
    agents: list[AgentViewModel]
    metrics: dict[str, float]

# 方法
model.export_viewmodel(format="json", viewport=None)
# format: "json" → bytes, "dict" → dict
# viewport: 可选 {"u_min": ..., "u_max": ..., "v_min": ..., "v_max": ...}
```
