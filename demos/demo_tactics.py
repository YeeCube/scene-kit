"""足球战术草稿盘 —— M3「战术板垂直模板」验收场景。

世界里有两类实体：
- ``player``：22 名球员（team=0 蓝方 / team=1 红方），带 r/g/b 颜色列；
- ``ball``：球（中圈开球位）。

静态场景（无行为注册）：战术推演由用户拖拽 + 阵型模板命令驱动，
对应 Layer 1 验收剧本「排兵—推演—表达」（20260830 会话 Pair 12）。

使用 ``--serve`` 时交给 ModelSession / Scene Studio 交互。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from scene_kit import EntityKind, WorldModel, WorldPlugin

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count

PITCH_U = 105.0
PITCH_V = 68.0

# 蓝方（team=0）初始站位：左半场粗略 4-3-3
BLUE_START = [
    (5, 34), (20, 10), (20, 26), (20, 42), (20, 58),
    (38, 17), (38, 34), (38, 51), (52, 12), (52, 34), (52, 56),
]


class TacticsPlugin(WorldPlugin):
    """战术板插件：声明 player 与 ball 两类实体。"""

    name = "tactics"

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = {"pitch_u": PITCH_U, "pitch_v": PITCH_V, **dict(config or {})}

    def register_kinds(self, w):
        w.register_kind(
            EntityKind("player", geometry="point", tags={"team": np.float32, "energy": np.float32})
        )
        w.register_kind(EntityKind("ball", geometry="point", tags={"energy": np.float32}))

    def register_resources(self, w):
        w.add_resource(dict(self.config))


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建静态战术盘：蓝方左半场、红方右半场镜像、球在中圈。"""
    values = {"pitch_u": PITCH_U, "pitch_v": PITCH_V, **dict(config or {})}
    pu = float(values["pitch_u"])
    pv = float(values["pitch_v"])

    model = WorldModel()
    model.add_root_surface(pu, pv)
    model.add_plugin(TacticsPlugin(values))

    blue_u = np.array([p[0] for p in BLUE_START], dtype=np.float32)
    blue_v = np.array([p[1] for p in BLUE_START], dtype=np.float32)
    red_u = (pu - blue_u).astype(np.float32)
    red_v = blue_v.copy()

    model.spawn(
        "player",
        n=11,
        u=blue_u,
        v=blue_v,
        team=0.0,
        r=40, g=90, b=220,
        size=3.0,
    )
    model.spawn(
        "player",
        n=11,
        u=red_u,
        v=red_v,
        team=1.0,
        r=220, g=60, b=60,
        size=3.0,
    )
    model.spawn("ball", n=1, u=np.float32(pu / 2), v=np.float32(pv / 2), r=250, g=250, b=250, size=1.8)
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "足球战术草稿盘", default_ticks=1)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="足球战术草稿盘", config=config, host=args.host, port=args.port, rate=args.rate, prefer_delta=args.delta)
        return

    model = create_model(config)
    print("=== 足球战术草稿盘（M3 战术板验收场景） ===\n")
    print(f"kinds: {model.list_kinds()}")
    print(f"WorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("静态场景：阵型模板/轨迹记录/导出由 Scene Studio 战术工具条驱动。")


if __name__ == "__main__":
    main()
