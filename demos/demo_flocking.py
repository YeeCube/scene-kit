"""Boids 群集 v0.3.0 —— 用 WorldPlugin 封装一种可复用的鸟群模型。

这个 demo 展示两件事：
1. 如何把实体类型、行为和配置资源打包成一个 WorldPlugin。
2. 如何直接使用 BehaviorRegistry 内置的 flocking 行为，而不是手写 Boids 更新逻辑。

默认会创建 100 只 bird，并推进 50 个 tick。使用 ``--serve`` 时，模型不会预先
运行，而是交给 ModelSession 和 World Model Studio 进行运行、暂停、单步和检查。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from scene_kit import EntityKind, WorldModel, WorldPlugin

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count


class FlockingPlugin(WorldPlugin):
    """鸟群插件：集中声明实体类型、行为注册和 demo 配置。"""

    name = "flocking"

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = {"size": 200, "n_birds": 100, **dict(config or {})}

    def register_kinds(self, w):
        """注册 bird 类型，并用 vx/vy 标签保存每只鸟的速度向量。"""
        w.register_kind(
            EntityKind("bird", geometry="point", tags={"vx": np.float32, "vy": np.float32})
        )

    def register_behaviors(self, w):
        """给 bird 绑定内置 flocking 行为。

        separation 控制近距离排斥，alignment 控制速度方向趋同，
        cohesion 控制向邻居中心靠拢，radius 是邻居搜索半径。
        """
        w.behaviors.flocking(
            "bird", separation=1.5, alignment=1.0, cohesion=1.0, radius=5.0, max_speed=2.0
        )

    def register_resources(self, w):
        """把 demo 参数写入资源表，便于主流程和 Studio 统一读取。"""
        w.add_resource(dict(self.config))


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建尚未推进 tick 的鸟群模型，导入模块时不会自动运行。"""
    values = {"size": 200, "n_birds": 100, "seed": 42, **dict(config or {})}
    size = float(values["size"])
    n_birds = int(values["n_birds"])
    rng = np.random.default_rng(int(values["seed"]))

    # 创建世界后添加插件，插件会自动完成 kind、behavior 和 resource 的注册。
    model = WorldModel(seed=int(values["seed"]))
    model.add_root_surface(size, size, boundary_u="toroidal", boundary_v="toroidal")
    model.add_plugin(FlockingPlugin(values))

    # angles 是每只鸟的初始朝向角；vx/vy 由这个角度转换成速度向量。
    angles = rng.uniform(0, 2 * np.pi, n_birds)
    model.spawn(
        "bird",
        n=n_birds,
        u=rng.uniform(0, size, n_birds),
        v=rng.uniform(0, size, n_birds),
        vx=np.cos(angles) * 2.0,
        vy=np.sin(angles) * 2.0,
        r=60,
        g=180,
        b=220,
        size=2.5,
    )
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "Boids 群集", default_ticks=50)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="Boids 群集", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    cfg = model.get_resource(dict)
    print("=== Boids 群集 v0.3.0 ===\n")
    print(f"plugin: {FlockingPlugin.name}, birds: {cfg['n_birds']}")
    print(f"kinds: {model.list_kinds()}")
    # model.run 会连续调用 step；这里用短运行展示插件行为已经接入调度系统。
    model.run(args.ticks)
    print(f"\n{args.ticks} ticks: {model._lifecycle['bird'].active_count} birds active")
    print(f"WorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
