"""ViewModel 导出 —— 将 WorldModel 状态序列化为前端可消费格式。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from scene_kit.world import WorldModel


@dataclass
class AgentViewModel:
    """v0.2 兼容的单个 Entity 调试表示。

    Attributes:
        id: Entity ID。
        kind: kind 名称。
        position: 世界坐标 [x, y, z]。
        r/g/b/a: 颜色 + 透明度。
        size: 显示大小。
        heading: 朝向角（弧度，None = 不适用）。
        shape: 形状标识 "circle" / "triangle" / "square"。
    """

    id: int
    kind: str
    position: list[float]
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255
    size: float = 3.0
    heading: float | None = None
    shape: str = "circle"


@dataclass
class WorldViewModel:
    """整个世界的可视化快照。

    Attributes:
        tick: 当前 tick。
        agents: 所有活跃 agent 的 ViewModel 列表。
        metrics: 自定义指标 dict。
    """

    tick: int
    agents: list[AgentViewModel] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def _to_native(val: Any) -> Any:
    """将 NumPy 标量转换为 Python 原生类型。"""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def export_viewmodel(
    model: "WorldModel",
    format: str = "json",
    viewport: dict | None = None,
) -> bytes | dict:
    """导出当前 tick 的 WorldViewModel。

    Args:
        model: WorldModel 实例。
        format: 序列化格式。"json" 返回 bytes，"dict" 返回 Python dict。
        viewport: 可选视口裁剪参数 {"u_min", "u_max", "v_min", "v_max"}。

    Returns:
        JSON bytes 或 Python dict。
    """
    agents: list[AgentViewModel] = []

    for kind_name in model.list_kinds():
        lm = model._lifecycle.get(kind_name)
        if lm is None:
            continue
        active = lm.active_indices
        if len(active) == 0:
            continue

        pool = model._bridge.get_pool(kind_name)

        # 读取位置列 (u, v) 或 (u, v, w)
        u_col = pool.d.get("u", None)
        v_col = pool.d.get("v", None)
        w_col = pool.d.get("w", None)

        if u_col is None or v_col is None:
            continue

        # 视口裁剪
        if viewport is not None:
            u_vals = u_col[active]
            v_vals = v_col[active]
            mask = (u_vals >= viewport.get("u_min", -np.inf)) & \
                   (u_vals <= viewport.get("u_max", np.inf)) & \
                   (v_vals >= viewport.get("v_min", -np.inf)) & \
                   (v_vals <= viewport.get("v_max", np.inf))
            visible = active[mask]
        else:
            visible = active

        for idx in visible:
            pos: list[float] = [float(u_col[idx]), float(v_col[idx])]
            if w_col is not None:
                pos.append(float(w_col[idx]))

            r = int(pool.d["r"][idx]) if "r" in pool.d else 255
            g = int(pool.d["g"][idx]) if "g" in pool.d else 255
            b = int(pool.d["b"][idx]) if "b" in pool.d else 255
            a = int(pool.d["a"][idx]) if "a" in pool.d else 255

            size_val = float(pool.d.get("size", pool.d.get("_size"))[idx]) \
                if "size" in pool.d or "_size" in pool.d else 3.0

            heading_val = float(pool.d["heading"][idx]) \
                if "heading" in pool.d else None

            uid = pool.d["i"][idx] if "i" in pool.d else idx
            try:
                uid = pool.backend.to_numpy(uid)
            except Exception:
                pass
            agents.append(AgentViewModel(
                id=int(uid),
                kind=kind_name,
                position=pos,
                r=r, g=g, b=b, a=a,
                size=size_val,
                heading=heading_val,
            ))

    vm = WorldViewModel(
        tick=model.tick,
        agents=agents,
        metrics=model._collector.evaluate_metrics(model) if model._collector is not None else {},
    )

    if format == "dict":
        return {
            "tick": vm.tick,
            "agents": [
                {
                    "id": a.id, "kind": a.kind, "position": a.position,
                    "r": a.r, "g": a.g, "b": a.b, "a": a.a,
                    "size": a.size, "heading": a.heading, "shape": a.shape,
                }
                for a in vm.agents
            ],
            "metrics": vm.metrics,
        }

    # 兼容 JSON 的逻辑结构不再根据实体数量静默变化。
    return json.dumps({
        "tick": vm.tick,
        "agents": [
            {
                "id": a.id, "kind": a.kind, "position": a.position,
                "r": a.r, "g": a.g, "b": a.b, "a": a.a,
                "size": a.size, "heading": a.heading, "shape": a.shape,
            }
            for a in vm.agents
        ],
        "metrics": vm.metrics,
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
