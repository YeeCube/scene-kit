# world-model-kit API 参考

> **版本**: 0.1.0 | **最后更新**: 2026-07-15

本文档列出 world-model-kit 所有公开 API 的签名、参数和返回值。按模块组织。

---

## 主入口

### `WorldModel`

```python
from world_model_kit import WorldModel

model = WorldModel(
    world_width: float = 100.0,
    world_height: float = 100.0,
    backend: str = "numpy",       # "numpy" | "torch" | "mlx" | "jax" | "auto"
    seed: int | None = None,
)
```

#### 类型注册

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `register_kind` | `(kind: EntityKind) -> None` | — |
| `unregister_kind` | `(name: str) -> None` | — |
| `list_kinds` | `() -> list[str]` | kind 名称列表 |

#### Agent 生命周期

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `spawn` | `(kind: str, n: int = 1, **attrs) -> np.ndarray` | 新 Agent 的 pool 索引数组 |
| `activate` | `(ids: np.ndarray) -> None` | — |
| `deactivate` | `(ids: np.ndarray) -> None` | — |
| `kill` | `(ids: np.ndarray) -> None` | — |
| `get_pool` | `(kind: str) -> EntityPool` | RECS EntityPool 实例 |

#### 空间操作

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `move` | `(ids: np.ndarray, dx, dy) -> None` | — |
| `move_to` | `(ids: np.ndarray, target_x, target_y) -> None` | — |
| `move_toward` | `(ids, target_x, target_y, max_distance) -> None` | — |
| `clamp_to_world` | `(ids: np.ndarray) -> None` | — |
| `wrap_toroidal` | `(ids: np.ndarray) -> None` | — |
| `bounce` | `(ids: np.ndarray) -> None` | — |
| `distance` | `(a_ids, b_ids) -> np.ndarray` | 成对距离 (len = min(len(a), len(b))) |
| `distance_matrix` | `(a_ids, b_ids) -> np.ndarray` | 全对距离矩阵 (len(a) × len(b)) |
| `nearest` | `(ids, x, y, k: int = 1) -> np.ndarray` | 最近邻索引 (len(ids) × k) |
| `within_radius` | `(ids, x, y, r) -> list[np.ndarray]` | 每个查询点的邻居索引列表 |
| `rotate` | `(ids: np.ndarray, angle: float) -> None` | — |
| `face_toward` | `(ids, target_x, target_y) -> None` | — |

#### 调度

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `step` | `() -> None` | — |
| `run` | `(ticks: int) -> None` | — |
| `step_for` | `(kind: str) -> Callable` | 装饰器 |
| `set_scheduler` | `(kind: str, scheduler: SchedulerBase) -> None` | — |

#### 数据采集

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `collect` | `(kind: str, fields: list[str]) -> None` | — |
| `aggregate` | `(kind_field: str, ops: str | list[str]) -> None` | — |
| `snapshot_every` | `(ticks: int) -> None` | — |
| `add_metric` | `(name: str, fn: Callable) -> None` | — |

#### 导出

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `export_dataframe` | `() -> pd.DataFrame` | 所有采集数据的 DataFrame |
| `export_numpy` | `() -> dict[str, np.ndarray]` | NumPy 结构化数据 |
| `export_viewmodel` | `() -> WorldViewModel` | 前端 ViewModel |
| `export_networkx` | `() -> nx.Graph` | NetworkX 图 |

#### 环境

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `set_space` | `(space: SpaceBase) -> None` | — |
| `add_field` | `(name: str, initial: float, **kw) -> None` | — |
| `add_obstacle_rect` | `(x, y, w, h) -> None` | — |

---

## `EntityKind`

```python
from world_model_kit import EntityKind

EntityKind(
    name: str,                        # 类型名
    position: bool = False,           # x, y (float32)
    position_3d: bool = False,        # + z (float32)
    velocity: bool = False,           # vx, vy (float32)
    heading: bool = False,            # heading (float32)
    speed: bool = False,              # speed (float32)
    energy: bool = False,             # energy (float32)
    age: bool = False,                # age (int32)
    color: bool = False,              # r, g, b (uint8 × 3)
    size: bool = False,               # size (float32)
    team: bool = False,               # team (int32)
    group: bool = False,              # group (int32)
    state: bool = False,              # state (int32)
    state_timer: bool = False,        # state_timer (int32)
    custom: dict[str, Any] = {},      # 自定义字段
)
```

---

## 空间模块

### `space/`

```python
from world_model_kit.space import ContinuousSpace, GridSpace, GraphSpace

ContinuousSpace(
    world_width: float,
    world_height: float,
    boundary: str = "clamp",    # "clamp" | "toroidal" | "bounce"
)

GridSpace(
    width: int,                 # 网格列数
    height: int,                # 网格行数
    cell_size: float = 1.0,
    boundary: str = "clamp",
)

GraphSpace(
    adjacency: np.ndarray,      # N×N 邻接矩阵
    node_positions: np.ndarray | None = None,  # N×2 节点坐标（可选）
)
```

---

## 空间嵌入模块

### `embedding/`

```python
from world_model_kit.embedding import embed_to, detach, reattach

# 嵌入
embed_to(entity_ids, parent_id, method="nearest")  # "nearest" | "at_t" | "at_uv"
detach(entity_ids)
reattach(entity_ids, new_parent_id)

# 约束运动
model.move_along_curve(ids, distance: float)
model.move_on_surface(ids, du: float, dv: float)
model.move_in_volume(ids, dx, dy, dz)

# 几何创建
model.create_curve(name: str, points: list[tuple]) -> Curve
model.create_surface(name: str, mesh: ...) -> Surface
model.create_volume(name: str, voxels: ...) -> Volume

# 交集检测
model.points_on_curve(agent_ids, curve_id, max_distance: float)
model.points_on_surface(agent_ids, surface_id)
model.intersecting_pairs(kind_a: str, kind_b: str)
model.intersects(entity_a, entity_b) -> bool
```

---

## 调度模块

### `schedule/`

```python
from world_model_kit.schedule import (
    RandomScheduler, SequentialScheduler,
    ByKindScheduler, ParallelScheduler,
    PhaseScheduler, EventQueueScheduler,
)

RandomScheduler(seed: int | None = None)
SequentialScheduler()
ByKindScheduler(kind_order: list[str])
ParallelScheduler()
PhaseScheduler(phases: list[str], transitions: dict)
EventQueueScheduler()
```

---

## 数据采集模块

### `collect/`

```python
from world_model_kit.collect import DataCollector, AggregateCollector

DataCollector(max_ticks: int = 10000)
# 方法: add_agent_fields, add_aggregate, snapshot_every, record_tick,
#       to_dataframe, to_numpy

AggregateCollector()
# 聚合操作: "mean", "std", "min", "max", "sum", "count"
```

---

## 行为模块

### `behaviors/`

```python
from world_model_kit.behaviors import (
    random_walk, flocking, pursuit_evasion,
    diffusion, contagion, competition,
)

random_walk(model, kind, step_size=1.0, angle_std=np.pi/4)

flocking(model, kind,
    separation_weight=1.5, alignment_weight=1.0,
    cohesion_weight=1.0, perception_radius=5.0, max_speed=2.0)

pursuit_evasion(model,
    pursuers="predator", evaders="prey",
    capture_radius=2.0, escape_speed=2.0, chase_speed=2.5)

diffusion(model, kind, diffusion_rate=0.1)

contagion(model, kind,
    infection_radius=1.5, infection_prob=0.3,
    recovery_ticks=100, initial_infected=1)
```

---

## 事件模块

### `events/`

```python
from world_model_kit.events import EventBus, EventType, EventLedger

# 事件类型
EventType.ENTITY_SPAWNED
EventType.ENTITY_ACTIVATED
EventType.ENTITY_DEACTIVATED
EventType.ENTITY_KILLED
EventType.TICK_START
EventType.TICK_END
EventType.EMBED_CHANGED
EventType.COLLISION

# 事件总线
model.events.subscribe(EventType.ENTITY_SPAWNED, handler)
model.events.unsubscribe(EventType.ENTITY_SPAWNED, handler)

# 事件账本（可选）
ledger = EventLedger(model)
ledger.record(event_type, tick, payload)
ledger.replay(model)
```

---

## ViewModel 导出

### `viewmodel/`

```python
from world_model_kit.viewmodel import export_viewmodel

@dataclass
class AgentViewModel:
    id: int; kind: str; x: float; y: float; z: float | None
    r: int; g: int; b: int; size: float; heading: float | None
    shape: str

@dataclass
class WorldViewModel:
    tick: int; world_width: float; world_height: float
    agents: list[AgentViewModel]; curves: list[CurveViewModel]
    surfaces: list[dict]; fields: list[FieldViewModel]
    obstacles: list[dict]; metrics: dict[str, float]

export_viewmodel(model: WorldModel) -> WorldViewModel
```

序列化：
```python
import json
vm = model.export_viewmodel()
json_str = json.dumps(vm)                         # JSON
import msgpack
msgpack_bytes = msgpack.packb(vm)                 # MessagePack
```

---

## 导出模块

```python
from world_model_kit.export import (
    to_dataframe, to_networkx, to_nlogo, to_mesa_model,
)

to_dataframe(model) -> pd.DataFrame
to_networkx(model) -> nx.Graph
to_nlogo(model, filepath: str) -> None
to_mesa_model(model) -> MesaModel
```
