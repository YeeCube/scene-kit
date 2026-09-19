"""跳棋草稿盘 —— M2「逻辑吸附」验收场景（ADR-002 D3）。

世界里有两类实体：
- ``slot``：9×9 棋盘落点（point geometry），是吸附目标；
- ``piece``：棋子，初始摆在棋盘下方的备战区。

没有注册任何行为——这是一个"静态草稿盘"，用来验证：
1. 拖拽棋子到落点附近，开启吸附后 ``snap_to_slots`` 对齐坐标并生成 ``is_on`` 关系边；
2. 关系边随 WorldSnapshot.relationBatches 到达前端；
3. despawn 棋子时级联清理其出入边。

使用 ``--serve`` 时交给 ModelSession / Scene Studio 交互。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from scene_kit import EntityKind, WorldModel, WorldPlugin

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count


class CheckersPlugin(WorldPlugin):
    """跳棋草稿盘插件：声明 slot 与 piece 两类实体。"""

    name = "checkers"

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = {"grid": 9, "cell": 10.0, **dict(config or {})}

    def register_kinds(self, w):
        w.register_kind(EntityKind("slot", geometry="point", tags={"energy": np.float32}))
        w.register_kind(EntityKind("piece", geometry="point", tags={"energy": np.float32}))

    def register_resources(self, w):
        w.add_resource(dict(self.config))


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建静态跳棋草稿盘：grid×grid 个落点 + 8 枚棋子（备战区）。"""
    values = {"grid": 9, "cell": 10.0, **dict(config or {})}
    grid = int(values["grid"])
    cell = float(values["cell"])
    board = grid * cell

    model = WorldModel()
    model.add_root_surface(board + 2 * cell, board + 3 * cell)
    model.add_plugin(CheckersPlugin(values))

    # 落点：棋盘格交点，浅灰色小点
    su, sv = np.meshgrid(
        np.arange(grid) * cell + cell,
        np.arange(grid) * cell + cell,
        indexing="ij",
    )
    model.spawn(
        "slot",
        n=grid * grid,
        u=su.ravel().astype(np.float32),
        v=sv.ravel().astype(np.float32),
        r=120,
        g=120,
        b=130,
        size=1.5,
    )

    # 棋子：4 白 4 黑，摆在棋盘下方备战区
    piece_u = np.array([20.0, 40.0, 60.0, 80.0, 20.0, 40.0, 60.0, 80.0], dtype=np.float32)
    piece_v = np.full(8, board + 1.5 * cell, dtype=np.float32)
    colors = np.array(
        [[235, 235, 240]] * 4 + [[40, 40, 50]] * 4, dtype=np.uint8
    )
    model.spawn(
        "piece",
        n=8,
        u=piece_u,
        v=piece_v,
        r=colors[:, 0].astype(np.int32),
        g=colors[:, 1].astype(np.int32),
        b=colors[:, 2].astype(np.int32),
        size=4.0,
    )
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "跳棋草稿盘", default_ticks=1)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="跳棋草稿盘", config=config, host=args.host, port=args.port, rate=args.rate, prefer_delta=args.delta)
        return

    model = create_model(config)
    print("=== 跳棋草稿盘（逻辑吸附验收场景） ===\n")
    print(f"kinds: {model.list_kinds()}")
    print(f"WorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("静态场景：无行为注册，交互由 Scene Studio 的 select/snap_to_slots 命令驱动。")


if __name__ == "__main__":
    main()
