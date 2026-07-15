"""Predator-Prey 演示 —— world-model-kit 烟雾测试。

500 prey + 20 predator, 200 ticks.
展示了最基础的用法：EntityKind 注册、spawn、step_for、空间操作。

用法::

    python demos/demo_predator_prey.py
"""

import numpy as np
from world_model_kit import WorldModel, EntityKind

# ---------------------------------------------------------------------------
# 1. 创建世界
# ---------------------------------------------------------------------------
model = WorldModel(world_width=200, world_height=200, backend="numpy", seed=42)

# ---------------------------------------------------------------------------
# 2. 定义 Agent 类型
# ---------------------------------------------------------------------------
prey = EntityKind("prey", position=True, velocity=True, energy=True, color=True)
predator = EntityKind("predator", position=True, velocity=True, energy=True, color=True)

model.register_kind(prey)
model.register_kind(predator)

# ---------------------------------------------------------------------------
# 3. 初始化
# ---------------------------------------------------------------------------
N_PREY = 500
N_PREDATOR = 20

model.spawn(
    "prey", n=N_PREY,
    x=np.random.uniform(0, 200, N_PREY),
    y=np.random.uniform(0, 200, N_PREY),
    vx=np.random.uniform(-1, 1, N_PREY),
    vy=np.random.uniform(-1, 1, N_PREY),
    energy=50.0,
    r=0, g=200, b=0,
)

model.spawn(
    "predator", n=N_PREDATOR,
    x=np.random.uniform(0, 200, N_PREDATOR),
    y=np.random.uniform(0, 200, N_PREDATOR),
    vx=0.0, vy=0.0,
    energy=100.0,
    r=220, g=30, b=30,
)

# ---------------------------------------------------------------------------
# 4. 定义行为
# ---------------------------------------------------------------------------

@model.step_for("prey")
def prey_step(m, ids):
    """prey: 随机游走 + 避开捕食者方向。"""
    # 随机游走
    angle = np.random.uniform(0, 2 * np.pi, len(ids))
    speed = 1.5
    m.move("prey", ids, np.cos(angle) * speed, np.sin(angle) * speed)
    m.clamp_to_world("prey", ids)


@model.step_for("predator")
def predator_step(m, ids):
    """predator: 向最近的 prey 移动。"""
    prey_active = m._lifecycle["prey"].active_indices
    if len(prey_active) == 0:
        return

    # 计算 prey 的质心作为追逐目标
    prey_x = m.attr("prey", "x")[prey_active]
    prey_y = m.attr("prey", "y")[prey_active]
    center_x = float(prey_x.mean())
    center_y = float(prey_y.mean())

    # 向质心移动
    m.move_toward("predator", ids, center_x, center_y, max_distance=2.5)
    m.clamp_to_world("predator", ids)

    # 捕食：检查每个 predator 半径内的 prey
    pred_x = m.attr("predator", "x")[ids]
    pred_y = m.attr("predator", "y")[ids]
    for i, pid in enumerate(ids):
        nearby_prey = m.within_radius(
            "prey", prey_active,
            cx=pred_x[i], cy=pred_y[i], radius=3.0,
        )
        if len(nearby_prey) > 0:
            m.kill("prey", nearby_prey[:1])  # 每次吃一只

# ---------------------------------------------------------------------------
# 5. 运行
# ---------------------------------------------------------------------------
TICKS = 200
print(f"Running {TICKS} ticks...")
print(f"  Initial: prey={N_PREY}, predator={N_PREDATOR}")

model.run(ticks=TICKS)

final_prey = model._lifecycle["prey"].active_count
final_predator = model._lifecycle["predator"].active_count

print(f"  Final:   prey={final_prey}, predator={final_predator}")
print(f"  Prey survival rate: {final_prey / N_PREY * 100:.1f}%")

# ---------------------------------------------------------------------------
# 6. 输出统计
# ---------------------------------------------------------------------------
prey_x = model.attr("prey", "x")[model._lifecycle["prey"].active_indices]
prey_y = model.attr("prey", "y")[model._lifecycle["prey"].active_indices]

print(f"\nPrey position stats:")
print(f"  x: mean={prey_x.mean():.1f}, std={prey_x.std():.1f}")
print(f"  y: mean={prey_y.mean():.1f}, std={prey_y.std():.1f}")

print("\nDone.")
