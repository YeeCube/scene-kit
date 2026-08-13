"""Scheduler 实现 —— 多种调度策略。

控制 Agent 的 step 执行顺序。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from scene_kit.world import WorldModel


class SchedulerBase(ABC):
    """调度器抽象基类。"""

    @abstractmethod
    def get_step_order(self, model: "WorldModel") -> list[str]:
        """返回本次 tick 的 kind 执行顺序。"""
        ...

    @abstractmethod
    def get_active_order(
        self, model: "WorldModel", kind: str, active_ids: np.ndarray
    ) -> np.ndarray:
        """返回 kind 内活跃 entity 的执行顺序。"""
        ...


class SequentialScheduler(SchedulerBase):
    """创建顺序调度（v0.1.0 默认行为）。"""

    def get_step_order(self, model: "WorldModel") -> list[str]:
        return list(model._step_order)

    def get_active_order(
        self, model: "WorldModel", kind: str, active_ids: np.ndarray
    ) -> np.ndarray:
        return active_ids


class RandomScheduler(SchedulerBase):
    """每 tick 随机 shuffle（适合生态仿真）。

    Args:
        seed: 随机种子（可选）。
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.RandomState(seed)

    def get_step_order(self, model: "WorldModel") -> list[str]:
        order = list(model._step_order)
        self._rng.shuffle(order)
        return order

    def get_active_order(
        self, model: "WorldModel", kind: str, active_ids: np.ndarray
    ) -> np.ndarray:
        result = active_ids.copy()
        self._rng.shuffle(result)
        return result


class ByKindScheduler(SchedulerBase):
    """Kind 分组内部 shuffle，不改变 kind 之间的顺序。"""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = np.random.RandomState(seed)

    def get_step_order(self, model: "WorldModel") -> list[str]:
        return list(model._step_order)

    def get_active_order(
        self, model: "WorldModel", kind: str, active_ids: np.ndarray
    ) -> np.ndarray:
        result = active_ids.copy()
        self._rng.shuffle(result)
        return result


class PhaseScheduler(SchedulerBase):
    """阶段机调度（回合制）。

    按阶段分组执行，每个阶段内的 kind 顺序执行。

    Args:
        phases: 阶段定义 dict。{"combat": ["pursuer", "evader"], "resolve": ["score"]}
    """

    def __init__(self, phases: dict[str, list[str]]) -> None:
        self.phases = phases
        self.current_phase: str = list(phases.keys())[0] if phases else ""

    def set_phase(self, phase: str) -> None:
        """切换到指定阶段。"""
        if phase not in self.phases:
            raise ValueError(f"未知阶段: {phase!r}, 可用: {list(self.phases.keys())}")
        self.current_phase = phase

    def get_step_order(self, model: "WorldModel") -> list[str]:
        return self.phases.get(self.current_phase, [])

    def get_active_order(
        self, model: "WorldModel", kind: str, active_ids: np.ndarray
    ) -> np.ndarray:
        return active_ids
