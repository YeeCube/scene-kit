"""捕食者-猎物模型 v0.3.0 —— 用最少 API 搭出空间生态仿真。

这个 demo 不是严格的 Lotka-Volterra 微分方程实现，而是一个离散空间版本：
1. prey 在平面内随机游走。
2. predator 朝所有猎物的平均位置移动。
3. predator 靠近 prey 时会 kill 一个猎物。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from scene_kit import EntityKind, WorldModel

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建尚未运行的捕食者—猎物模型。"""
    values = {"size": 200, "n_prey": 300, "n_predator": 15, "seed": 42, **dict(config or {})}
    size = float(values["size"])
    n_prey = int(values["n_prey"])
    n_predator = int(values["n_predator"])
    rng = np.random.default_rng(int(values["seed"]))

    # 使用 numpy 后端创建二维世界；边界随后通过 clamp_to_world 处理。
    model = WorldModel(backend="numpy", seed=int(values["seed"]))
    model.add_root_surface(size, size)
    model.add_resource(values)

    # energy/vx/vy 展示如何给 Entity 扩展领域属性。
    tags = {"energy": np.float32, "vx": np.float32, "vy": np.float32}
    model.register_kind(EntityKind("prey", geometry="point", tags=tags))
    model.register_kind(EntityKind("predator", geometry="point", tags=tags))

    # 批量生成时，颜色用于前端区分绿色猎物和红色捕食者。
    model.spawn(
        "prey", n=n_prey,
        u=rng.uniform(0, size, n_prey), v=rng.uniform(0, size, n_prey),
        vx=rng.uniform(-1, 1, n_prey), vy=rng.uniform(-1, 1, n_prey),
        energy=50.0, r=0, g=200, b=0, size=2.0,
    )
    model.spawn(
        "predator", n=n_predator,
        u=rng.uniform(0, size, n_predator), v=rng.uniform(0, size, n_predator),
        vx=0.0, vy=0.0, energy=100.0, r=220, g=30, b=30, size=3.5,
    )

    @model.step_for("prey")
    def prey_step(m, ids):
        """猎物每个 tick 随机选择方向移动，并被限制在世界边界内。"""
        angle = rng.uniform(0, 2 * np.pi, len(ids))
        m.move("prey", ids, np.column_stack([np.cos(angle) * 1.5, np.sin(angle) * 1.5]))
        m.clamp_to_world("prey", ids)

    @model.step_for("predator")
    def predator_step(m, ids):
        """捕食者朝猎物群中心移动，并吃掉半径 3 内的一个猎物。"""
        active_prey = m._lifecycle["prey"].active_indices
        if len(active_prey) == 0:
            return
        prey_u = m.attr("prey", "u")[active_prey]
        prey_v = m.attr("prey", "v")[active_prey]
        m.move_toward("predator", ids, float(prey_u.mean()), float(prey_v.mean()), max_distance=2.5)
        m.clamp_to_world("predator", ids)
        predator_u, predator_v = m.attr("predator", "u")[ids], m.attr("predator", "v")[ids]
        for index, _predator_id in enumerate(ids):
            neighbors = m.within_radius(
                "prey", active_prey, cx=predator_u[index], cy=predator_v[index], radius=3.0
            )
            if len(neighbors) > 0:
                m.kill("prey", neighbors[:1])

    return model


def main() -> None:
    parser = demo_parser(__doc__ or "捕食者-猎物", default_ticks=200)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="捕食者-猎物", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    initial = model._lifecycle["prey"].active_count
    model.run(args.ticks)
    final_prey = model._lifecycle["prey"].active_count
    final_predators = model._lifecycle["predator"].active_count
    print(f"prey: {initial} -> {final_prey} ({final_prey / initial * 100:.0f}%), predator: {final_predators}")
    print(f"WorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
