"""群体行为仿真 v0.3.0 —— 手写 Boids 规则并记录涌现指标。

这个 demo 与 demo_flocking.py 形成对照：那里使用内置 flocking 行为，
这里直接在 step 函数中实现简化版 Boids。读者可以看到完整的数据流：
1. 用 tags 保存速度、能量和邻居数量。
2. 每个 tick 根据邻居计算分离和对齐。
3. 用 DataCollector 记录速度统计和自定义的全局对齐度。

世界边界使用 toroidal 环面，即 Entity 从右侧离开会从左侧进入。
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scene_kit import EntityKind, WorldModel

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count


def alignment_order(model: WorldModel) -> float:
    """计算全局对齐度。

    指标接近 1 表示绝大多数 boid 朝同一方向运动；接近 0 表示方向近似随机。
    """
    # active 是所有活跃 boid 的行索引；没有 Entity 时约定对齐度为 0。
    active = model._lifecycle["boid"].active_indices
    if len(active) == 0:
        return 0.0
    velocity_x = model.attr("boid", "vx")[active]
    velocity_y = model.attr("boid", "vy")[active]
    speed = np.sqrt(velocity_x**2 + velocity_y**2)
    if speed.sum() == 0:
        return 0.0
    return float(
        np.sqrt(
            (velocity_x / (speed + 1e-6)).mean() ** 2
            + (velocity_y / (speed + 1e-6)).mean() ** 2
        )
    )


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建手写 Boids 模型；所有模型状态仍存储在 RECS SoA 列中。"""
    values = {
        "size": 200, "n_boids": 120, "radius": 50.0, "max_speed": 4.0, "seed": 42,
        **dict(config or {}),
    }
    size = float(values["size"])
    count = int(values["n_boids"])
    radius = float(values["radius"])
    max_speed = float(values["max_speed"])
    rng = np.random.default_rng(int(values["seed"]))

    # 创建带环面边界的二维世界，适合观察连续空间里的群体运动。
    model = WorldModel(seed=int(values["seed"]))
    model.add_root_surface(size, size, boundary_u="toroidal", boundary_v="toroidal")
    model.add_resource(values)

    # n_neighbors 是派生标签：每个 tick 根据当前空间关系重新计算。
    boid = EntityKind(
        "boid", geometry="point",
        tags={
            "vx": np.float32, "vy": np.float32,
            "energy": np.float32, "n_neighbors": np.int32,
        },
    )
    model.register_kind(boid)

    # angles 是每个 boid 的初始朝向角，用来生成 vx/vy 初始速度分量。
    angles = rng.uniform(0, 2 * np.pi, count)
    model.spawn(
        "boid", n=count,
        u=rng.uniform(0, size, count), v=rng.uniform(0, size, count),
        vx=np.cos(angles) * 3.0, vy=np.sin(angles) * 3.0, energy=50.0,
        n_neighbors=np.zeros(count, dtype=np.int32), r=60, g=160, b=220, size=2.5,
    )

    @model.step_for("boid")
    def boid_step(current_model, ids):
        """执行一轮简化 Boids 更新。

        本函数只实现分离和对齐两项，省略显式聚合项；即便如此，局部相互作用
        仍然足以产生从随机运动到局部有序的过渡。
        """
        # u/v 是位置数组；vx/vy 是速度数组。转成 float64 可以降低中间计算误差。
        position_u = current_model.attr("boid", "u")[ids].astype(np.float64)
        position_v = current_model.attr("boid", "v")[ids].astype(np.float64)
        velocity_x = current_model.attr("boid", "vx")[ids].astype(np.float64)
        velocity_y = current_model.attr("boid", "vy")[ids].astype(np.float64)
        count_active = len(ids)
        next_x, next_y = velocity_x.copy(), velocity_y.copy()
        for index in range(count_active):
            # 环面空间里的最短位移：跨越边界的 Entity 也应被视为近邻。
            delta_u, delta_v = position_u - position_u[index], position_v - position_v[index]
            delta_u = np.where(delta_u > size / 2, delta_u - size, np.where(delta_u < -size / 2, delta_u + size, delta_u))
            delta_v = np.where(delta_v > size / 2, delta_v - size, np.where(delta_v < -size / 2, delta_v + size, delta_v))
            distance = np.sqrt(delta_u**2 + delta_v**2)
            neighbors = (distance > 0) & (distance < radius)
            current_model.set_attr("boid", "n_neighbors", np.array([ids[index]]), neighbors.sum())
            if neighbors.sum() < 2:
                continue
            # 分离规则：当邻居过近时，沿远离邻居的方向加速，避免个体重叠。
            close = distance[neighbors] < radius * 0.25
            if close.any():
                close_u, close_v = delta_u[neighbors][close], delta_v[neighbors][close]
                close_distance = distance[neighbors][close] + 1e-6
                next_x[index] += (-close_u / close_distance).mean() * 2.5
                next_y[index] += (-close_v / close_distance).mean() * 2.5
            # 对齐规则：把自己的速度缓慢拉向邻居平均速度。
            next_x[index] += (velocity_x[neighbors].mean() - velocity_x[index]) * 0.4
            next_y[index] += (velocity_y[neighbors].mean() - velocity_y[index]) * 0.4

        # 限速保证仿真稳定，避免少数 Entity 因为叠加强力规则而飞出合理范围。
        speed = np.sqrt(next_x**2 + next_y**2)
        too_fast = speed > max_speed
        next_x[too_fast] *= max_speed / speed[too_fast]
        next_y[too_fast] *= max_speed / speed[too_fast]
        current_model.set_attr("boid", "vx", ids, next_x.astype(np.float32))
        current_model.set_attr("boid", "vy", ids, next_y.astype(np.float32))
        current_model.move("boid", ids, np.column_stack([next_x.astype(np.float32), next_y.astype(np.float32)]))
        current_model.wrap_toroidal("boid", ids)

    # collector 可以同时记录基础标签统计和任意 Python 指标函数。
    model.collector.aggregate("boid", "vx", ["mean", "std"])
    model.collector.add_metric("alignment", alignment_order)
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "群体行为", default_ticks=200)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="群体行为", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    print("=== 群体行为 v0.3.0 ===\n")
    for tick in range(1, args.ticks + 1):
        model.step()
        if tick % 40 == 0:
            order = alignment_order(model)
            state = "有序" if order > 0.7 else "过渡" if order > 0.3 else "随机"
            print(f"  tick {tick:3d}: 对齐度={order:.3f} {state}")
    print(f"\nWorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
