"""Behaviors 子模块 —— 内置行为的向量化实现。"""

from scene_kit.behaviors.registry import BehaviorRegistry
from scene_kit.behaviors.random_walk import random_walk
from scene_kit.behaviors.flocking import flocking
from scene_kit.behaviors.pursuit_evasion import pursuit_evasion

__all__ = [
    "BehaviorRegistry",
    "random_walk",
    "flocking",
    "pursuit_evasion",
]
