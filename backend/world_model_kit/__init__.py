"""world-model-kit — 世界模型工具包。

基于 RECS（SoA ECS 引擎）的高性能 Agent-Based Modeling 工具包。
提供 EntityKind 属性预设、Agent 生命周期管理、空间嵌入、
约束运动、交集检测、调度系统、数据采集与 ViewModel 导出。

三层接入策略：
- L1 Raw: RECS EntityPool 直通
- L2 API: WorldModel + EntityKind + step_for 装饰器
- L3 DSL: 内置行为一键注册（behaviors.flocking 等）

主入口::

    from world_model_kit import WorldModel, EntityKind
"""

from world_model_kit._version import __version__
from world_model_kit.entity_kind import EntityKind
from world_model_kit.world import WorldModel

__all__ = [
    "__version__",
    "WorldModel",
    "EntityKind",
]
