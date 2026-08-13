"""scene-kit — Scene Suite 伞形品牌下的开源 SDK（SceneKit · 场景工具包）。

基于 RECS（SoA ECS 引擎）的高性能场景建模工具包。
提供 geometry 驱动的嵌套 Entity 树、tags 语义标注、Perception 感知框架、
调度器、内置行为、数据采集与 SoA WorldSnapshot 导出。

四层接入策略：
- L0 Expression: 内置行为一键注册（model.behaviors.flocking("bird")）
- L1 Raw: RECS EntityPool 直通（model.get_pool(kind)）
- L2 API: WorldModel + EntityKind + step_for 装饰器
- L3 Plugin: WorldPlugin 封装（model.add_plugin(MyPlugin())）

主入口::

    from scene_kit import WorldModel, EntityKind, WorldPlugin
"""

from scene_kit._version import __version__
from scene_kit.entity_kind import EntityKind
from scene_kit.world import WorldModel
from scene_kit.plugins.base import WorldPlugin
from scene_kit.perception import Perception
from scene_kit.protocol import SnapshotProjection
from scene_kit.runner import ModelSession

__all__ = [
    "__version__",
    "WorldModel",
    "EntityKind",
    "WorldPlugin",
    "Perception",
    "SnapshotProjection",
    "ModelSession",
]
