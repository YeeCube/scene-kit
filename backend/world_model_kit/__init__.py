"""world-model-kit — 世界模型工具包 v0.2.0。

基于 RECS（SoA ECS 引擎）的高性能 Agent-Based Modeling 工具包。
提供 geometry 驱动的嵌套 Entity 树、tags 语义标注、Perception 感知框架、
调度器、内置行为、数据采集与 ViewModel 导出。

v0.2.0 核心变更：从扁平 2D (x,y) 世界升级为 geometry + parent + tags 体系。

四层接入策略：
- L0 Expression: 内置行为一键注册（model.behaviors.flocking("bird")）
- L1 Raw: RECS EntityPool 直通（model.get_pool(kind)）
- L2 API: WorldModel + EntityKind + step_for 装饰器
- L3 Plugin: WorldPlugin 封装（model.add_plugin(MyPlugin())）

主入口::

    from world_model_kit import WorldModel, EntityKind, WorldPlugin
"""

from world_model_kit._version import __version__
from world_model_kit.entity_kind import EntityKind
from world_model_kit.world import WorldModel
from world_model_kit.plugins.base import WorldPlugin
from world_model_kit.perception import Perception

__all__ = [
    "__version__",
    "WorldModel",
    "EntityKind",
    "WorldPlugin",
    "Perception",
]
