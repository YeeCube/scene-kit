"""YG 游戏引擎集成 Demo —— 追捕躲藏对战。

演示 YG 如何使用 world-model-kit 作为 Agent 后端：
- 多 kind（pursuer + evader + obstacle）
- 阵营系统（team 属性）
- 阶段机调度（部署阶段 → 战斗阶段 → 结算阶段）
- 游戏特有属性（HP、attack、capture_count）
- 游戏规则（合法性检查、得分统计）

用法::

    python demos/demo_yge_game.py
"""

import numpy as np
from world_model_kit import WorldModel, EntityKind

# ===================================================================
# 1. YG 特色：注册游戏特有的 Agent 类型
# ===================================================================
model = WorldModel(world_width=100, world_height=100, backend="numpy", seed=2026)

pursuer_kind = EntityKind("pursuer",
    position=True, velocity=True, heading=True,
    team=True,
    color=True,
    custom={
        "hp": np.float32,           # 生命值
        "attack": np.float32,       # 攻击力
        "capture_count": np.int32,  # 捕获数
    },
)
evader_kind = EntityKind("evader",
    position=True, velocity=True, heading=True,
    team=True,                      # 阵营 1 = 红方
    color=True,
    custom={
        "hp": np.float32,
        "evasion": np.float32,      # 闪避率
        "survived_ticks": np.int32,
    },
)
obstacle_kind = EntityKind("obstacle",
    position=True,
    color=True, size=True,
    custom={"block_radius": np.float32},
)

model.register_kind(pursuer_kind)
model.register_kind(evader_kind)
model.register_kind(obstacle_kind)

# ===================================================================
# 2. YG 特色：按阵营部署 + 阶段机调度
# ===================================================================
N_P = 5   # pursuer 数
N_E = 10  # evader 数

# 蓝方 pursuer
model.spawn("pursuer", n=N_P,
    x=np.random.uniform(5, 40, N_P), y=np.random.uniform(5, 95, N_P),
    hp=100.0, attack=15.0, capture_count=0,
    team=0, heading=0.0, r=30, g=100, b=220,
)
# 红方 evader
model.spawn("evader", n=N_E,
    x=np.random.uniform(60, 95, N_E), y=np.random.uniform(5, 95, N_E),
    hp=80.0, evasion=0.3, survived_ticks=0,
    team=1, heading=np.pi, r=220, g=50, b=50,
)
# 中立障碍物
model.spawn("obstacle", n=8,
    x=np.random.uniform(20, 80, 8), y=np.random.uniform(20, 80, 8),
    block_radius=np.random.uniform(3, 6, 8),
    team=-1, r=100, g=100, b=100, size=6.0,
)

# ===================================================================
# 3. YG 特色：游戏规则 + 阶段机
# ===================================================================
phase = {"current": "deploy"}   # deploy → combat → resolve
CAPTURE_RADIUS = 6.0
MAX_TICKS = 100

@model.step_for("pursuer")
def pursuer_step(m, ids):
    if phase["current"] != "combat":
        return

    evader_active = m._lifecycle["evader"].active_indices
    if len(evader_active) == 0:
        phase["current"] = "resolve"
        return

    px = m.attr("pursuer", "x")[ids]
    py = m.attr("pursuer", "y")[ids]
    ex = m.attr("evader", "x")[evader_active]
    ey = m.attr("evader", "y")[evader_active]

    for i, pid in enumerate(ids):
        dists = np.sqrt((ex - px[i])**2 + (ey - py[i])**2)
        nearest_j = np.argmin(dists)
        nearest_idx = evader_active[nearest_j]

        if dists[nearest_j] <= CAPTURE_RADIUS:
            m.kill("evader", np.array([nearest_idx]))
            m.attr("pursuer", "capture_count")[pid] += 1
        else:
            m.move_toward("pursuer", np.array([pid]),
                float(ex[nearest_j]), float(ey[nearest_j]),
                max_distance=3.0)

    m.clamp_to_world("pursuer", ids)


@model.step_for("evader")
def evader_step(m, ids):
    if phase["current"] != "combat":
        return

    # YG 特色：逃跑策略（远离最近的 pursuer）
    pursuer_active = m._lifecycle["pursuer"].active_indices
    if len(pursuer_active) == 0:
        return

    px = m.attr("pursuer", "x")[pursuer_active]
    py = m.attr("pursuer", "y")[pursuer_active]
    ex = m.attr("evader", "x")[ids]
    ey = m.attr("evader", "y")[ids]

    for i, eid in enumerate(ids):
        dists = np.sqrt((px - ex[i])**2 + (py - ey[i])**2)
        nearest_idx = np.argmin(dists)
        # 远离最近的 pursuer
        dx = ex[i] - px[nearest_idx]
        dy = ey[i] - py[nearest_idx]
        dist = max(dists[nearest_idx], 1e-6)
        m.move("evader", np.array([eid]), dx / dist * 1.5, dy / dist * 1.5)

    m.attr("evader", "survived_ticks")[ids] += 1
    m.clamp_to_world("evader", ids)


@model.step_for("obstacle")
def obstacle_step(m, ids):
    pass  # 障碍物不动

# ===================================================================
# 4. 运行
# ===================================================================
print("=== YG 追捕躲藏对战 ===\n")

print(f"[部署阶段] pursuer × {N_P} | evader × {N_E} | obstacle × 8")
phase["current"] = "combat"
print("[战斗阶段] 开始...")

for tick in range(1, MAX_TICKS + 1):
    model.step()
    evader_alive = model._lifecycle["evader"].active_count
    if tick % 10 == 0 or evader_alive == 0:
        captures = model.attr("pursuer", "capture_count")[
            model._lifecycle["pursuer"].active_indices
        ]
        print(f"  tick {tick:3d}: evader alive = {evader_alive}, "
              f"total captures = {captures.sum()}")

    if evader_alive == 0:
        phase["current"] = "resolve"
        break

# ===================================================================
# 5. YG 特色：对局结算
# ===================================================================
print(f"\n[结算阶段]")
captures = model.attr("pursuer", "capture_count")[
    model._lifecycle["pursuer"].active_indices
]
print(f"  蓝方总捕获数: {captures.sum()}/{N_E}")
print(f"  蓝方 MVP: pursuer#{np.argmax(captures)} = {captures.max()} captures")

survived = model.attr("evader", "survived_ticks")[
    model._lifecycle["evader"].active_indices
]
if len(survived) > 0:
    print(f"  红方存活: {len(survived)} 人, 最长存活 {survived.max()} ticks")

print("\n=== YG Demo 完成 ===")
print("下一步：YG 前端通过 WebSocket bridge 获取 tick 数据，")
print("用 viewport-2d-kit 管相机 + Canvas 画单位/技能特效/HUD。")
