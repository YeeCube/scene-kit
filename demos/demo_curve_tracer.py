"""曲线追踪 v0.3.0 —— 动点沿数学曲线运动，并实时记录切线与法线。

这个 demo 适合用来理解“几何对象 + 自定义标签”的组合方式：
1. trail Entity 保存整条 Lissajous 曲线的采样点，用于可视化曲线轨迹。
2. tracer Entity 是唯一的运动点，它的 t 标签表示当前曲线参数。
3. tan_x/tan_y 与 norm_x/norm_y 展示如何把派生数学量写回 Entity 标签。

注意：WorldModel 的显示坐标以左上角为原点，因此这里把数学坐标 y
转换为屏幕坐标时使用了 C - y。
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


# SIZE 是世界边长；C 是世界中心点坐标，也就是数学坐标原点映射到屏幕后的偏移。
SIZE, C = 12.0, 6.0


def curve(t):
    """返回 Lissajous 参数曲线上的点。

    Args:
        t: 曲线参数，可以是单个浮点数，也可以是 NumPy 数组。

    Returns:
        二元组 ``(x, y)``，分别表示数学坐标系中的横坐标和纵坐标。

    Examples:
        ``x, y = curve(0.0)`` 会返回曲线在起点参数处的位置。
    """
    return 5 * np.sin(2 * t), 5 * np.cos(3 * t)


def tangent(t):
    """返回参数曲线在 t 处的导数，也就是未归一化的切向量。

    Args:
        t: 曲线参数，可以是单个浮点数，也可以是 NumPy 数组。

    Returns:
        二元组 ``(dx_dt, dy_dt)``，表示参数曲线对 t 的导数。
    """
    return 10 * np.cos(2 * t), -15 * np.sin(3 * t)


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建曲线、静态参照点和 tracer，但不自动推进模型。"""
    values = {"size": SIZE, "trail_points": 300, "axis_points": 40, "seed": 0, **dict(config or {})}
    size = float(values["size"])
    center = size / 2
    trail_points = int(values["trail_points"])
    axis_points = int(values["axis_points"])

    # 建立一个小世界，中心点对应数学坐标原点。
    model = WorldModel(seed=int(values["seed"]))
    model.add_root_surface(size, size)
    model.add_resource(values)

    # tracer 需要保存当前参数 t，以及用于可视化或后续计算的单位切线/法线。
    # trail 和 axis 只是静态点集，因此不需要额外标签。
    model.register_kind(
        EntityKind(
            "tracer", geometry="point",
            tags={
                "t": np.float32, "tan_x": np.float32, "tan_y": np.float32,
                "norm_x": np.float32, "norm_y": np.float32,
            },
        )
    )
    model.register_kind(EntityKind("trail", geometry="point", tags={}, type="OBJECT"))
    model.register_kind(EntityKind("axis", geometry="point", tags={}, type="OBJECT"))

    # ts 是用于绘制静态轨迹的参数采样点，数量越多，曲线越平滑。
    # cx/cy 是数学坐标系中的采样结果，spawn 时再映射到世界坐标。
    ts = np.linspace(0, 2 * np.pi, trail_points)
    cx, cy = curve(ts)
    model.spawn("trail", n=trail_points, u=cx + center, v=center - cy, r=100, g=180, b=255, size=0.08)

    # ax 是坐标轴采样点。这里用点 Entity 拼出 x 轴和 y 轴，避免引入额外绘图组件。
    ax = np.linspace(-center, center, axis_points)
    model.spawn("axis", n=axis_points, u=ax + center, v=np.full(axis_points, center), r=150, g=150, b=150, size=0.05)
    model.spawn("axis", n=axis_points, u=np.full(axis_points, center), v=center - ax, r=150, g=150, b=150, size=0.05)

    # t0 是 tracer 的初始曲线参数；px/py 是初始数学坐标。
    # tx/ty 是初始切向量；tl 是切向量长度，用来归一化切线和法线标签。
    t0 = 0.0
    px, py = curve(t0)
    tx, ty = tangent(t0)
    tangent_length = np.sqrt(tx**2 + ty**2)
    model.spawn(
        "tracer", n=1, u=px + center, v=center - py, t=t0,
        tan_x=tx / tangent_length, tan_y=-ty / tangent_length,
        norm_x=ty / tangent_length, norm_y=tx / tangent_length,
        r=255, g=80, b=80, size=0.2,
    )

    @model.step_for("tracer")
    def tracer_step(m, ids):
        """每个 tick 推进曲线参数，并写回位置、单位切线和单位法线。

        Args:
            m: 当前 ``WorldModel`` 实例，行为函数通过它读取和修改 Entity 状态。
            ids: 本轮需要更新的 tracer 行索引数组；本 demo 中长度始终为 1。
        """
        # t 是旧参数，nt 是推进后的新参数；取模让动点沿闭合曲线循环运动。
        t = m.attr("tracer", "t")[ids]
        next_t = (t + 0.08) % (2 * np.pi)
        # px2/py2 是新位置；tx2/ty2 是新切向量；tl2 用于得到单位向量。
        px2, py2 = curve(next_t)
        tx2, ty2 = tangent(next_t)
        length = np.sqrt(tx2**2 + ty2**2)
        m.move_to("tracer", ids, px2 + center, center - py2)
        m.set_attr("tracer", "t", ids, next_t)
        m.set_attr("tracer", "tan_x", ids, tx2 / length)
        m.set_attr("tracer", "tan_y", ids, -ty2 / length)
        m.set_attr("tracer", "norm_x", ids, ty2 / length)
        m.set_attr("tracer", "norm_y", ids, tx2 / length)

    @model.step_for("trail")
    def trail_step(_m, _ids):
        """保持静态参考轨迹不变。"""

    @model.step_for("axis")
    def axis_step(_m, _ids):
        """保持静态坐标轴点集不变。"""

    return model


def main() -> None:
    parser = demo_parser(__doc__ or "曲线追踪", default_ticks=80)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="曲线追踪", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    tracer_id = model._lifecycle["tracer"].active_indices[0]
    print("=== 曲线追踪 v0.3.0 ===\n")
    for tick in range(1, args.ticks + 1):
        model.step()
        if tick % 10 == 0:
            # 每 10 个 tick 打印一次当前参数和切线，方便在无可视化窗口时检查结果。
            value_t = float(model.attr("tracer", "t")[tracer_id])
            tangent_x = float(model.attr("tracer", "tan_x")[tracer_id])
            tangent_y = float(model.attr("tracer", "tan_y")[tracer_id])
            print(f"  tick {tick:2d}: t={value_t:.2f} 切线=({tangent_x:+.3f},{tangent_y:+.3f})")
    print(f"\nWorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
