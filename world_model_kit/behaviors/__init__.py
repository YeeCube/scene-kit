"""Behaviors 子模块 —— 内置行为的向量化实现。"""

from world_model_kit.behaviors.registry import BehaviorRegistry
from world_model_kit.behaviors.random_walk import random_walk
from world_model_kit.behaviors.flocking import flocking
from world_model_kit.behaviors.pursuit_evasion import pursuit_evasion

__all__ = [
    "BehaviorRegistry",
    "random_walk",
    "flocking",
    "pursuit_evasion",
]
