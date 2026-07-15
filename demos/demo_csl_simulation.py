"""CSL 复杂系统实验室集成 Demo —— 交通拥堵波仿真。

演示 CSL 如何使用 world-model-kit 作为科学仿真后端：
- 路网空间（一维环形道路 + 多车道）
- 车辆跟驰模型（IDM 简化版）
- 领域特有度量（交通流量、平均车速、拥堵波速）
- 批处理输出（每 tick 的统计数据 → CSV/论文图表）

用法::

    python demos/demo_csl_simulation.py
"""

import numpy as np
from world_model_kit import WorldModel, EntityKind

# ===================================================================
# 1. CSL 特色：路网 + 车辆 Agent
# ===================================================================
ROAD_LENGTH = 1000.0        # 环形道路长度（米）
NUM_VEHICLES = 80
SAFE_DIST = 25.0            # 安全跟车距离
MAX_SPEED = 14.0            # 最大速度 (m/s ≈ 50 km/h)
ACCEL = 2.0                 # 最大加速度
DECEL = 4.0                 # 舒适减速度

model = WorldModel(world_width=ROAD_LENGTH, world_height=10, seed=2026)

vehicle_kind = EntityKind("vehicle",
    position=True,              # x = 沿路位置, y = 车道号
    velocity=True,              # vx = 速度
    color=True,
    custom={
        "desired_speed": np.float32,  # 期望速度
        "lane": np.int32,             # 当前车道
    },
)
model.register_kind(vehicle_kind)

# ===================================================================
# 2. CSL 特色：按分布初始化车辆
# ===================================================================
# 车辆初始位置：均匀分布 + 小幅随机扰动
positions = np.sort(np.random.uniform(0, ROAD_LENGTH, NUM_VEHICLES))
# 初始速度：期望速度的 60-100%
initial_speeds = np.random.uniform(0.6, 1.0, NUM_VEHICLES) * MAX_SPEED

model.spawn("vehicle", n=NUM_VEHICLES,
    x=positions,
    y=np.zeros(NUM_VEHICLES),   # 单车道
    vx=initial_speeds,
    desired_speed=np.random.uniform(0.8, 1.0, NUM_VEHICLES) * MAX_SPEED,
    lane=np.zeros(NUM_VEHICLES, dtype=np.int32),
    r=50, g=120, b=220,
)

# ===================================================================
# 3. CSL 特色：IDM 跟驰模型（简化版）
# ===================================================================
@model.step_for("vehicle")
def vehicle_step(m, ids):
    """简化跟驰模型 —— 按与前车距离调整速度。

    环形道路上，每辆车根据它与前车的 gap 决定加减速。
    """
    x = m.attr("vehicle", "x")[ids]
    v = m.attr("vehicle", "vx")[ids]
    v0 = m.attr("vehicle", "desired_speed")[ids]
    n_cars = len(ids)

    if n_cars <= 1:
        dv = np.clip(v0 - v, -ACCEL, ACCEL)
        new_v = np.clip(v + dv * 0.5, 0, MAX_SPEED)
        m.attr("vehicle", "vx")[ids] = new_v
        m.move("vehicle", ids, new_v, 0.0)
        m.wrap_toroidal("vehicle", ids)
        return

    # 按位置排序
    sort_idx = np.argsort(x)
    sorted_ids = ids[sort_idx]
    sorted_x = x[sort_idx]
    sorted_v = v[sort_idx]
    sorted_v0 = v0[sort_idx]

    new_v = sorted_v.copy()
    for i in range(n_cars):
        j = (i + 1) % n_cars
        gap = sorted_x[j] - sorted_x[i]
        if gap <= 0:
            gap += ROAD_LENGTH

        # 简单跟驰：gap 足够大就加速到期望速度，太小就减速
        if gap > SAFE_DIST * 2:
            acc = ACCEL * (1 - sorted_v[i] / sorted_v0[i])
        elif gap > SAFE_DIST:
            acc = 0.0  # 匀速
        else:
            acc = -DECEL * (1 - gap / SAFE_DIST)

        new_v[i] = max(0.0, sorted_v[i] + acc * 0.5)

    # 写回
    inv_sort = np.argsort(sort_idx)
    m.attr("vehicle", "vx")[ids] = new_v[inv_sort]
    m.move("vehicle", ids, new_v[inv_sort], 0.0)

    # 环形世界绕回
    new_x = m.attr("vehicle", "x")[ids]
    new_x[new_x >= ROAD_LENGTH] -= ROAD_LENGTH
    new_x[new_x < 0] += ROAD_LENGTH


# ===================================================================
# 4. CSL 特色：采集领域度量
# ===================================================================
TICKS = 300
flow_history = []
speed_history = []
density_history = []

print("=== CSL 交通拥堵波仿真 ===\n")
print(f"环形道路 {ROAD_LENGTH}m × 1 车道, {NUM_VEHICLES} 辆车")
print(f"初始密度: {NUM_VEHICLES / ROAD_LENGTH * 1000:.1f} 辆/km")

for tick in range(1, TICKS + 1):
    model.step()

    # 每 30 ticks 采集一次度量（CSL 特色：科学统计节奏）
    if tick % 30 == 0:
        active = model._lifecycle["vehicle"].active_indices
        speeds = model.attr("vehicle", "vx")[active]
        positions = model.attr("vehicle", "x")[active]

        mean_speed = float(speeds.mean())
        # 流量 = 密度 × 平均速度（辆车每秒通过一个截面）
        density = len(active) / ROAD_LENGTH
        flow = density * mean_speed

        flow_history.append(flow)
        speed_history.append(mean_speed)
        density_history.append(density)

        congestion = "拥堵" if mean_speed < 5.0 else ("通畅" if mean_speed > 10.0 else "缓行")
        print(f"  tick {tick:3d}: 均速={mean_speed:.1f} m/s | "
              f"密度={density*1000:.1f} 辆/km | 流量={flow:.2f} 辆/s | {congestion}")

# ===================================================================
# 5. CSL 特色：导出论文级统计
# ===================================================================
print(f"\n=== CSL 仿真报告 ===")
print(f"道路长度:     {ROAD_LENGTH} m")
print(f"车辆数:       {NUM_VEHICLES}")
print(f"仿真 ticks:   {TICKS}")
print(f"采样间隔:     30 ticks")
print(f"\n时间序列统计 (均值 ± 标准差):")
print(f"  平均车速:   {np.mean(speed_history):.2f} ± {np.std(speed_history):.2f} m/s")
print(f"  车流密度:   {np.mean(density_history)*1000:.1f} ± {np.std(density_history)*1000:.1f} 辆/km")
print(f"  交通流量:   {np.mean(flow_history):.2f} ± {np.std(flow_history):.2f} 辆/s")
print(f"  最低车速:   {np.min(speed_history):.2f} m/s （拥堵波谷）")
print(f"  最高车速:   {np.max(speed_history):.2f} m/s （自由流）")

print(f"\n=== CSL Demo 完成 ===")
print("下一步：CSL 前端用 HTTPBridge 获取 tick 数据，")
print("用 viewport-2d-kit 管相机 + Canvas 画道路/车辆/热力图，")
print("导出 PNG → 论文插图。")
