"""Kuramoto 相振子模型 v0.3.0 —— 用相位有序度观察同步趋势。

这个 demo 建立 oscillator Entity，每个 Entity 保存 phase（当前相位）和
freq（个体固有频率）。EntityKind 同时声明 perceive 配置，演示 Entity 如何
描述“我能感知谁”。当前 step 函数保留为简化模型；可以继续加入邻居耦合项。
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


def order_param(model: WorldModel) -> float:
    """计算 Kuramoto 常用的相位有序度 R。

    R 接近 1 表示大多数振子相位一致，R 接近 0 表示相位分布较分散。
    没有活跃振子时返回 0.0。
    """
    # active 是参与统计的活跃振子行索引。
    active = model._lifecycle["oscillator"].active_indices
    if len(active) == 0:
        return 0.0
    # phase 是相位数组；sin/cos 的均值长度就是 Kuramoto order parameter。
    phase = model.attr("oscillator", "phase")[active]
    return float(np.sqrt(np.sin(phase).mean() ** 2 + np.cos(phase).mean() ** 2))


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建尚未推进的相振子模型。"""
    values = {"size": 200, "n_oscillators": 100, "seed": 42, **dict(config or {})}
    size = float(values["size"])
    count = int(values["n_oscillators"])
    rng = np.random.default_rng(int(values["seed"]))

    # 使用 numpy 后端创建二维世界；位置只用于空间演示，核心状态保存在 phase/freq 标签中。
    model = WorldModel(backend="numpy", seed=int(values["seed"]))
    model.add_root_surface(size, size, boundary_u="toroidal", boundary_v="toroidal")
    model.add_resource(values)

    # perceive 描述感知半径、目标类型和需要暴露给感知系统的自身标签。
    # 这让行为函数后续可以从感知结果里读取邻居相位，而不必自己扫描全局 Entity。
    oscillator = EntityKind(
        "oscillator",
        geometry="point",
        tags={"phase": np.float32, "freq": np.float32},
        perceive={"radius": 40.0, "of_kinds": ["oscillator"], "self_tags": ["phase"]},
    )
    model.register_kind(oscillator)

    # angles 是初始相位采样源；freq 是每个振子的固有频率。
    angles = rng.uniform(0, 2 * np.pi, count)
    model.spawn(
        "oscillator", n=count,
        u=rng.uniform(0, size, count), v=rng.uniform(0, size, count),
        phase=angles.astype(np.float32),
        freq=rng.uniform(0.8, 1.2, count).astype(np.float32),
        r=80, g=160, b=255, size=2.2,
    )

    @model.step_for("oscillator")
    def oscillator_step(current_model, _perception):
        """推进所有振子的相位，并让它们在平面上做轻微随机游走。

        参数 perception 由感知框架传入。这个基础 demo 暂未使用它，但保留参数
        可以展示配置 perceive 后，行为函数如何接收感知数据。
        """
        active = current_model._lifecycle["oscillator"].active_indices
        if len(active) == 0:
            return
        phase = current_model.attr("oscillator", "phase")[active]
        frequency = current_model.attr("oscillator", "freq")[active]
        next_phase = phase + frequency * 0.1
        # 随机游走让振子空间位置持续变化；环面边界避免在边缘堆积。
        angle = rng.uniform(0, 2 * np.pi, len(active))
        current_model.move(
            "oscillator", active, np.column_stack([np.cos(angle) * 0.5, np.sin(angle) * 0.5])
        )
        current_model.wrap_toroidal("oscillator", active)
        current_model.set_attr("oscillator", "phase", active, next_phase % (2 * np.pi))

    # 把自定义指标交给 collector，方便协议、Studio 和数据分析统一读取。
    model.collector.add_metric("order", order_param)
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "Kuramoto 相振子", default_ticks=100)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="Kuramoto 相振子", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    print("=== Kuramoto 相振子 v0.3.0 ===\n")
    for tick in range(1, args.ticks + 1):
        model.step()
        if tick % 20 == 0:
            order = order_param(model)
            state = "同步" if order > 0.7 else "去同步" if order < 0.3 else "过渡"
            print(f"  tick {tick:3d}: order R={order:.3f} {state}")
    print(f"\nWorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
