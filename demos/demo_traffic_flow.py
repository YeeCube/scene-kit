"""交通流仿真 v0.3.0 —— 双车道高速公路、跟驰和简单换道。

这个 demo 把道路建模成环形高速公路：u 表示沿道路前进的距离，v 表示车道位置，
boundary_u="toroidal" 表示车辆开到道路末端后会从起点重新进入。
行为规则是教学用的简化模型；DataCollector 记录速度统计。
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


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建双车道环形道路模型，不自动推进车辆。"""
    values = {"road_length": 500.0, "n_cars": 80, "speed_limit": 12.0, "seed": 2026, **dict(config or {})}
    road_length = float(values["road_length"])
    count = int(values["n_cars"])
    speed_limit = float(values["speed_limit"])
    rng = np.random.default_rng(int(values["seed"]))

    # u 方向为环面边界，模拟一条首尾相接的道路；v 方向夹紧。
    model = WorldModel(backend="numpy", seed=int(values["seed"]))
    model.add_root_surface(road_length, 4, boundary_u="toroidal", boundary_v="clamp")
    model.add_resource(values)

    # speed 是当前速度，pref_speed 是期望速度，lane 是离散车道编号。
    car = EntityKind(
        "car", geometry="point",
        tags={"speed": np.float32, "pref_speed": np.float32, "lane": np.int32},
    )
    model.register_kind(car)

    # positions 排序后让车流沿道路展开；speed 同时作为初始和期望速度。
    positions = np.sort(rng.uniform(0, road_length, count))
    speeds = rng.uniform(0.5, 1.0, count) * speed_limit
    lanes = np.where(rng.random(count) < 0.6, 0, 1).astype(np.int32)
    model.spawn(
        "car", n=count, u=positions,
        v=np.where(lanes == 0, 1.0, 3.0).astype(np.float32),
        speed=speeds, pref_speed=speeds, lane=lanes,
        r=50, g=120, b=220, size=2.5,
    )

    @model.step_for("car")
    def car_step(current_model, ids):
        """更新所有车辆的速度、车道和位置。

        这里使用一个很小的跟驰模型：只看排序后的下一辆车。如果同车道前车太近，
        当前车减速；否则逐步向期望速度恢复，并在低速时以小概率换道。
        """
        position = current_model.attr("car", "u")[ids]
        speed = current_model.attr("car", "speed")[ids]
        preferred = current_model.attr("car", "pref_speed")[ids]
        lane = current_model.attr("car", "lane")[ids]
        active_count = len(ids)
        sorted_indices = np.argsort(position)
        sorted_position = position[sorted_indices]
        sorted_speed = speed[sorted_indices]
        sorted_preferred = preferred[sorted_indices]
        sorted_lane = lane[sorted_indices]
        next_speed = sorted_speed.copy()
        for index in range(active_count):
            ahead = (index + 1) % active_count
            gap = sorted_position[ahead] - sorted_position[index]
            if gap <= 0:
                gap += road_length
            # 同车道跟驰：前车过近时按距离比例减速，保留最低速度避免完全停住。
            if sorted_lane[index] == sorted_lane[ahead] and gap < 20:
                next_speed[index] = max(1.0, sorted_speed[index] - 3.0 * (1 - gap / 20))
            else:
                next_speed[index] = min(
                    speed_limit,
                    sorted_speed[index] + 1.5 * (sorted_preferred[index] - sorted_speed[index]) / sorted_preferred[index],
                )
                # 慢车换道：真实模型还需要检查目标车道安全间距。
                if sorted_speed[index] < 4 and rng.random() < 0.2:
                    sorted_lane[index] = 1 - sorted_lane[index]

        # 恢复到 ids 原顺序再写回 SoA 列。
        inverse = np.argsort(sorted_indices)
        next_speed = next_speed[inverse]
        next_lane = sorted_lane[inverse]
        current_model.set_attr("car", "speed", ids, next_speed)
        current_model.set_attr("car", "lane", ids, next_lane)
        current_model.set_attr("car", "v", ids, np.where(next_lane == 0, 1.0, 3.0))
        current_model.move("car", ids, np.column_stack([next_speed, np.zeros(active_count, dtype=np.float32)]))
        current_model.wrap_toroidal("car", ids)

    # collector 既保存逐 tick 原始速度，也保存常用聚合统计。
    model.collector.collect("car", ["speed"])
    model.collector.aggregate("car", "speed", ["mean", "std", "min", "max"])
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "交通流", default_ticks=150)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="交通流", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    print("=== 交通流 v0.3.0 ===\n")
    for tick in range(1, args.ticks + 1):
        model.step()
        if tick % 30 == 0:
            # 均速下降通常意味着拥堵开始形成。
            active = model._lifecycle["car"].active_indices
            mean_speed = float(model.attr("car", "speed")[active].mean())
            print(f"  tick {tick:3d}: 均速={mean_speed:.1f} m/s")
    print(f"\nWorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
