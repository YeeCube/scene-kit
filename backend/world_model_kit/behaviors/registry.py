"""BehaviorRegistry —— 内置行为注册表。

通过 model.behaviors 访问，提供一键注册的内置向量化行为。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world_model_kit.world import WorldModel


class BehaviorRegistry:
    """内置行为注册表。

    通过 model.behaviors.flocking("bird") 等方式访问。
    每个方法注册一个 @step_for 函数。

    Attributes:
        _model: 关联的 WorldModel 实例。
    """

    def __init__(self, model: "WorldModel") -> None:
        self._model = model

    def random_walk(self, kind: str, step_size: float = 1.0) -> None:
        """注册随机游走行为。

        Args:
            kind: kind 名称。
            step_size: 步长。
        """
        from world_model_kit.behaviors.random_walk import random_walk as _rw
        _rw(self._model, kind, step_size)

    def flocking(
        self,
        kind: str,
        separation: float = 1.5,
        alignment: float = 1.0,
        cohesion: float = 1.0,
        radius: float = 5.0,
        max_speed: float = 2.0,
    ) -> None:
        """注册 Boids 群集行为。

        Args:
            kind: kind 名称。
            separation: 分离权重。
            alignment: 对齐权重。
            cohesion: 凝聚权重。
            radius: 感知半径。
            max_speed: 最大速度。
        """
        from world_model_kit.behaviors.flocking import flocking as _fl
        _fl(self._model, kind, separation, alignment, cohesion, radius, max_speed)

    def pursuit_evasion(
        self,
        pursuer_kind: str,
        evader_kind: str,
        capture_radius: float = 2.0,
        pursuit_speed: float = 1.5,
    ) -> None:
        """注册追捕-逃跑行为。

        Args:
            pursuer_kind: 追捕者 kind。
            evader_kind: 逃跑者 kind。
            capture_radius: 捕获半径。
            pursuit_speed: 追捕速度。
        """
        from world_model_kit.behaviors.pursuit_evasion import pursuit_evasion as _pe
        _pe(self._model, pursuer_kind, evader_kind, capture_radius, pursuit_speed)
