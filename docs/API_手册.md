# API_手册

> **版本**: 0.6.0 | **最后更新**: 2026-08-14

## v0.6 交互会话 API

`ModelSession` 是 Python 模型与界面的唯一可变状态边界。它接受 `play`、`pause`、`step`、`reset`、`set_rate`、`set_parameter`、`spawn`、`despawn`、`move`、`set_tag` 与 `set_attribute` 命令；命令结果均为 `CommandResult`。

```python
from scene_kit import ModelSession
from scene_kit.transport import serve_session

session = ModelSession(model, model_factory=create_model, parameters={"n_birds": 100})
await serve_session(session, prefer_delta=True)
```

WebSocket envelope 为 `hello`、`snapshot`、`delta`、`commandResult`、`error`，另支持 `getSnapshot` 与 `ping` 请求。服务默认只绑定 `127.0.0.1`；如需接入网关，可向 `serve_session(..., authorize=...)` 提供鉴权钩子。

---

## WorldModel

```python
from scene_kit import WorldModel

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

### Snapshot 导出

| 方法 | 签名 | 说明 |
|---|---|---|
| `export_snapshot` | `(projection=None, format="dict") -> dict \| bytes` | 导出固定 schema 的 RECS 风格 SoA 快照 |
| `export_viewmodel` | `(format="json", viewport=None) -> bytes \| dict` | v0.2 AoS 兼容/调试视图 |
| `export_dataframe` | `() -> pd.DataFrame` | 导出 DataCollector 记录 |

---

## EntityKind

```python
from scene_kit import EntityKind

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
from scene_kit.geometry import Geometry

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
from scene_kit.schedule import (
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

## WorldSnapshot / WorldDelta

```python
from scene_kit import SnapshotProjection

projection = SnapshotProjection(
    kinds=("bird",),
    columns=("u", "v", "r", "g", "b", "a"),
    viewport={"u_min": 0, "u_max": 200, "v_min": 0, "v_max": 200},
)
snapshot = model.export_snapshot(projection, format="dict")
```

快照的核心结构如下（字段名和列长度固定）：

```json
{
  "protocol": "wmk.world-snapshot",
  "protocolVersion": "1.0",
  "snapshotId": "snapshot-1",
  "tick": 0,
  "entityBatches": {
    "bird": {
      "kind": "bird",
      "geometry": "point",
      "count": 2,
      "schema": {"uid": {"dtype": "int64", "encoding": "decimal-string"}},
      "columns": {"uid": ["7", "8"], "u": [12.4, 18.0], "v": [8.1, 20.0]}
    }
  },
  "relationBatches": {},
  "metrics": {}
}
```

`WorldDelta` 使用 `baseSnapshotId` 和 `snapshotId`，在每个 kind 下表达 `removedUids`、`added` 和 `changed`。前端应以 `(kind, uid)` 作为实体引用，不应依赖批次中的数组索引。

### SnapshotProjection

| 字段 | 说明 |
|---|---|
| `kinds` | 仅导出指定 EntityKind；`None` 表示全部 |
| `columns` | 所有 kind 共用的列序列，或 `{kind: columns}` 映射；`uid` 始终导出 |
| `viewport` | `u_min/u_max/v_min/v_max` 视口过滤 |
| `include_relations` | 是否预留关系批次（当前关系导出能力有限） |
| `include_metrics` | 是否包含采集器指标 |
| `include_world_coordinates` | 是否补充递归世界坐标列 |

### ModelSession

```python
from scene_kit import ModelSession

session = ModelSession(model, model_factory=lambda cfg: make_model(cfg), parameters={"seed": 42})
session.dispatch({"type": "step", "payload": {"steps": 1}})
snapshot = session.snapshot()
```

`dispatch()` 立即处理命令；`enqueue_command()` 将命令放到下一次 `advance()` 的 tick 边界执行。`next_message(prefer_delta=True)` 在有上一快照时返回 `WorldDelta`，否则返回完整快照。

### WebSocketModelServer

```python
from scene_kit.transport import WebSocketModelServer

server = WebSocketModelServer(session, host="127.0.0.1", port=8765)
```

安装 `scene-kit[server]` 后运行 `serve_forever()`。客户端消息为 `getSnapshot` 或 `command`；服务端 envelope 类型为 `hello`、`snapshot`、`delta`、`commandResult`、`error`。

### 兼容接口

`AgentViewModel`、`WorldViewModel` 和 `export_viewmodel()` 属于 v0.2 兼容层。新代码不要围绕 `agents` 对象数组设计；请使用 `EntityBatch` 的列式结构。
