"""WorldPlugin —— Scene Kit 插件基类。

类似 Bevy 的 Plugin trait。子类重写 register_* 方法封装领域逻辑。
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scene_kit.world import WorldModel


class WorldPlugin(ABC):
    """Scene Kit 插件基类。

    子类重写四个 register_* 钩子来封装领域逻辑：
    - register_kinds: 注册 EntityKind
    - register_behaviors: 注册 @step_for 函数
    - register_collectors: 配置 DataCollector
    - register_resources: 注入全局资源（add_resource）

    Usage::

        class MyPlugin(WorldPlugin):
            name = "my_plugin"

            def register_kinds(self, world):
                world.register_kind(EntityKind("bird", geometry="point",
                    tags={"speed": np.float32}))

            def register_behaviors(self, world):
                world.behaviors.flocking("bird")

        model.add_plugin(MyPlugin())
    """

    name: str = "unnamed_plugin"

    def build(self, world: "WorldModel") -> None:
        """完整插件构建生命周期。依次调用四个钩子。"""
        self.register_kinds(world)
        self.register_behaviors(world)
        self.register_collectors(world)
        self.register_resources(world)

    def register_kinds(self, world: "WorldModel") -> None:
        """注册 EntityKind。子类重写。"""
        pass

    def register_behaviors(self, world: "WorldModel") -> None:
        """注册 @step_for 行为。子类重写。"""
        pass

    def register_collectors(self, world: "WorldModel") -> None:
        """配置 DataCollector。子类重写。"""
        pass

    def register_resources(self, world: "WorldModel") -> None:
        """注入全局资源。子类重写。"""
        pass
