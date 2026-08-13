"""Embedding 子模块 —— Entity 的动态宿主切换。

提供 embed_to / detach / reattach 操作。
"""

from scene_kit.embedding.operations import embed_to, detach, reattach

__all__ = ["embed_to", "detach", "reattach"]
