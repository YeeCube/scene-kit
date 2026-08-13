"""多人追逐游戏 v0.3.0 —— 用插件、标签和分步行为组织一个小型游戏。

场景中有 chaser、runner 和若干 barrier：
1. chaser 会追最近的 runner，并在距离小于 catch_radius 时移除对方。
2. runner 会远离最近的 chaser，并累计 survival_time。
3. barrier 作为静态障碍示例存在，方便读者扩展碰撞或遮挡规则。

重点是展示 WorldPlugin、tags、生命周期与 WorldSnapshot 如何组合。
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from scene_kit import EntityKind, WorldModel, WorldPlugin

from demos._runtime import demo_parser, parse_config, serve_demo, snapshot_entity_count


class ChaseGamePlugin(WorldPlugin):
    """追逐游戏插件：把游戏相关注册逻辑集中到一个可复用组件中。"""

    name = "chase_game"

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = {"game_ticks": 80, "catch_radius": 5.0, **dict(config or {})}

    def register_kinds(self, world):
        """注册三类 Entity 及其标签。

        chaser 的 score 记录抓到的 runner 数量；runner 的 stamina 预留给体力系统，
        survival_time 用来记录存活 tick；team 可用于扩展阵营过滤。
        """
        world.register_kind(
            EntityKind(
                "chaser", geometry="point",
                tags={"vx": np.float32, "vy": np.float32, "score": np.int32, "team": np.int32},
            )
        )
        world.register_kind(
            EntityKind(
                "runner", geometry="point",
                tags={
                    "vx": np.float32, "vy": np.float32, "stamina": np.float32,
                    "survival_time": np.int32, "team": np.int32,
                },
            )
        )
        world.register_kind(
            EntityKind("barrier", geometry="point", type="OBJECT", tags={"radius": np.float32, "team": np.int32})
        )

    def register_behaviors(self, world):
        """注册每一类 Entity 在单个 tick 内的行为。"""
        catch_radius = float(self.config["catch_radius"])

        @world.step_for("chaser")
        def chaser_step(model, ids):
            """追捕者寻找最近的 runner：够近就捕获，否则向目标移动。"""
            # runners 是当前仍然活跃的 runner 行索引；没有目标时直接结束。
            runners = model._lifecycle["runner"].active_indices
            if len(runners) == 0:
                return
            chaser_u, chaser_v = model.attr("chaser", "u")[ids], model.attr("chaser", "v")[ids]
            runner_u, runner_v = model.attr("runner", "u")[runners], model.attr("runner", "v")[runners]
            for index, chaser_id in enumerate(ids):
                distance = np.sqrt((runner_u - chaser_u[index]) ** 2 + (runner_v - chaser_v[index]) ** 2)
                nearest = int(np.argmin(distance))
                if distance[nearest] <= catch_radius:
                    # kill 会把 runner 标记为非活跃；后续 active_indices 不再包含它。
                    model.kill("runner", np.array([runners[nearest]]))
                    score = model.attr("chaser", "score")[chaser_id] + 1
                    model.set_attr("chaser", "score", np.array([chaser_id]), score)
                else:
                    model.move_toward(
                        "chaser", np.array([chaser_id]),
                        float(runner_u[nearest]), float(runner_v[nearest]), max_distance=2.5,
                    )
            model.clamp_to_world("chaser", ids)

        @world.step_for("runner")
        def runner_step(model, ids):
            """逃跑者远离最近的 chaser，并把存活时间加一。"""
            chasers = model._lifecycle["chaser"].active_indices
            if len(chasers) == 0:
                return
            chaser_u, chaser_v = model.attr("chaser", "u")[chasers], model.attr("chaser", "v")[chasers]
            runner_u, runner_v = model.attr("runner", "u")[ids], model.attr("runner", "v")[ids]
            for index, runner_id in enumerate(ids):
                distance = np.sqrt((chaser_u - runner_u[index]) ** 2 + (chaser_v - runner_v[index]) ** 2)
                nearest = int(np.argmin(distance))
                delta_x, delta_y = runner_u[index] - chaser_u[nearest], runner_v[index] - chaser_v[nearest]
                magnitude = max(distance[nearest], 1e-6)
                model.move(
                    "runner", np.array([runner_id]),
                    np.array([[delta_x / magnitude * 1.8, delta_y / magnitude * 1.8]]),
                )
            model.set_attr(
                "runner", "survival_time", ids,
                model.attr("runner", "survival_time")[ids] + 1,
            )
            model.clamp_to_world("runner", ids)

        @world.step_for("barrier")
        def barrier_step(_model, _ids):
            """保留静态障碍物；当前不移动。"""

    def register_resources(self, world):
        """注册 demo 参数，主流程和 Studio 通过资源表读取。"""
        world.add_resource(dict(self.config))


def create_model(config: Mapping[str, Any] | None = None) -> WorldModel:
    """创建追逐游戏的初始状态，不自动开始游戏。"""
    values = {
        "size": 120, "n_chasers": 5, "n_runners": 8, "n_barriers": 5,
        "game_ticks": 80, "catch_radius": 5.0, "seed": 2026,
        **dict(config or {}),
    }
    size = float(values["size"])
    n_chasers = int(values["n_chasers"])
    n_runners = int(values["n_runners"])
    n_barriers = int(values["n_barriers"])
    rng = np.random.default_rng(int(values["seed"]))

    model = WorldModel(seed=int(values["seed"]))
    model.add_root_surface(size, size)
    model.add_plugin(ChaseGamePlugin(values))

    model.spawn(
        "chaser", n=n_chasers,
        u=rng.uniform(10, size / 3, n_chasers), v=rng.uniform(10, size - 10, n_chasers),
        score=0, team=0, r=30, g=100, b=220, size=3.0,
    )
    model.spawn(
        "runner", n=n_runners,
        u=rng.uniform(size * 2 / 3, size - 10, n_runners), v=rng.uniform(10, size - 10, n_runners),
        stamina=rng.uniform(80, 120, n_runners).astype(np.float32),
        survival_time=0, team=1, r=220, g=50, b=50, size=2.5,
    )
    model.spawn(
        "barrier", n=n_barriers,
        u=rng.uniform(size / 4, size * 3 / 4, n_barriers),
        v=rng.uniform(size / 4, size * 3 / 4, n_barriers),
        radius=rng.uniform(4, 8, n_barriers).astype(np.float32),
        team=-1, r=100, g=100, b=100, size=4.0,
    )
    return model


def main() -> None:
    parser = demo_parser(__doc__ or "多人追逐游戏", default_ticks=80)
    args = parser.parse_args()
    config = parse_config(args.set)
    if args.serve:
        serve_demo(create_model, name="多人追逐游戏", config=config, host=args.host, port=args.port, rate=args.rate)
        return

    model = create_model(config)
    initial_runners = model._lifecycle["runner"].active_count
    print("=== 追逐游戏 v0.3.0 ===\n")
    for tick in range(1, args.ticks + 1):
        model.step()
        remaining = model._lifecycle["runner"].active_count
        if tick % 20 == 0 or remaining == 0:
            scores = model.attr("chaser", "score")[model._lifecycle["chaser"].active_indices]
            print(f"  tick {tick:3d}: runners={remaining}, total catches={scores.sum()}")
        if remaining == 0:
            break
    scores = model.attr("chaser", "score")[model._lifecycle["chaser"].active_indices]
    print(f"\ncatches: {scores.sum()}/{initial_runners}, top chaser score={scores.max()}")
    print(f"WorldSnapshot: {snapshot_entity_count(model)} entities in SoA batches")
    print("Done.")


if __name__ == "__main__":
    main()
