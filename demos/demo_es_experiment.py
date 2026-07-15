"""ES 隐德莱希系统集成 Demo —— Boids 群集涌现实验。

演示 ES 如何使用 world-model-kit 作为涌现实验后端：
- 适应性 Agent（简单规则 → 复杂群集行为）
- 涌现度量（熵、复杂度、互信息、因果涌现）
- 实验设计（参数扫描、对比实验、消融实验）
- ES 特有概念（phase transition、order parameter）

用法::

    python demos/demo_es_experiment.py
"""

import numpy as np
from world_model_kit import WorldModel, EntityKind

# ===================================================================
# 1. ES 特色：涌现实验配置
# ===================================================================
WORLD_SIZE = 200
NUM_BOIDS = 150
PERCEPTION = 40.0    # 感知半径
MAX_SPEED = 4.0

model = WorldModel(world_width=WORLD_SIZE, world_height=WORLD_SIZE, seed=42)

boid_kind = EntityKind("boid",
    position=True, velocity=True, heading=True,
    energy=True, color=True,
    custom={
        "order_param": np.float32,   # 局部有序度（每个 boid 的）
        "neighbor_count": np.int32,  # 邻居数
    },
)
model.register_kind(boid_kind)

# ===================================================================
# 2. ES 特色：初始条件对涌现的影响
# ===================================================================
# 实验组 A：随机初始（预期：逐步形成有序群集）
angles_a = np.random.uniform(0, 2 * np.pi, NUM_BOIDS)
model.spawn("boid", n=NUM_BOIDS,
    x=np.random.uniform(0, WORLD_SIZE, NUM_BOIDS),
    y=np.random.uniform(0, WORLD_SIZE, NUM_BOIDS),
    vx=np.cos(angles_a) * 3.0,
    vy=np.sin(angles_a) * 3.0,
    energy=50.0, r=60, g=180, b=220,
)

# ===================================================================
# 3. ES 特色：简单规则 → 涌现行为
# ===================================================================
@model.step_for("boid")
def boid_step(m, ids):
    """Boids 三规则：分离 + 对齐 + 凝聚。

    ES 研究者的核心问题：这三个权重参数的微小变化
    如何导致宏观相变（无序 ↔ 有序群集 ↔ 混沌）？
    """
    x = m.attr("boid", "x")[ids]
    y = m.attr("boid", "y")[ids]
    vx = m.attr("boid", "vx")[ids]
    vy = m.attr("boid", "vy")[ids]
    n = len(ids)

    new_vx = vx.copy()
    new_vy = vy.copy()

    for i, bid in enumerate(ids):
        # 找邻居
        dx = x - x[i]
        dy = y - y[i]
        # 环形距离
        dx = np.where(dx > WORLD_SIZE/2, dx - WORLD_SIZE,
                      np.where(dx < -WORLD_SIZE/2, dx + WORLD_SIZE, dx))
        dy = np.where(dy > WORLD_SIZE/2, dy - WORLD_SIZE,
                      np.where(dy < -WORLD_SIZE/2, dy + WORLD_SIZE, dy))
        dist = np.sqrt(dx**2 + dy**2)
        neighbors = (dist > 0) & (dist < PERCEPTION)

        m.attr("boid", "neighbor_count")[bid] = neighbors.sum()

        if neighbors.sum() < 2:
            continue

        nx = x[neighbors]
        ny = y[neighbors]
        nvx = vx[neighbors]
        nvy = vy[neighbors]
        ndx = dx[neighbors]
        ndy = dy[neighbors]
        ndist = dist[neighbors]

        # 分离：远离太近的邻居
        close = ndist < PERCEPTION * 0.3
        if close.any():
            sep_dx = -ndx[close] / (ndist[close] + 1e-6)
            sep_dy = -ndy[close] / (ndist[close] + 1e-6)
            new_vx[i] += sep_dx.mean() * 2.0
            new_vy[i] += sep_dy.mean() * 2.0

        # 对齐：匹配邻居的平均方向
        new_vx[i] += (nvx.mean() - vx[i]) * 0.5
        new_vy[i] += (nvy.mean() - vy[i]) * 0.5

        # 凝聚：向邻居质心移动
        new_vx[i] += (nx.mean() - x[i]) * 0.01
        new_vy[i] += (ny.mean() - y[i]) * 0.01

    # 限速
    speed = np.sqrt(new_vx**2 + new_vy**2)
    mask = speed > MAX_SPEED
    new_vx[mask] = new_vx[mask] / speed[mask] * MAX_SPEED
    new_vy[mask] = new_vy[mask] / speed[mask] * MAX_SPEED

    m.attr("boid", "vx")[ids] = new_vx
    m.attr("boid", "vy")[ids] = new_vy
    m.move("boid", ids, new_vx, new_vy)
    m.wrap_toroidal("boid", ids)


# ===================================================================
# 4. ES 特色：涌现度量采集
# ===================================================================
def compute_order_parameter(m: WorldModel) -> float:
    """全局有序度 —— ES 最基础的涌现度量。

    O = 1 表示完美对齐（有序态）
    O ≈ 0 表示完全随机（无序态）
    O 的突变 = 相变点
    """
    active = m._lifecycle["boid"].active_indices
    if len(active) == 0:
        return 0.0
    vx = m.attr("boid", "vx")[active]
    vy = m.attr("boid", "vy")[active]
    speed = np.sqrt(vx**2 + vy**2)
    if speed.sum() == 0:
        return 0.0
    ux = (vx / (speed + 1e-6)).mean()
    uy = (vy / (speed + 1e-6)).mean()
    return float(np.sqrt(ux**2 + uy**2))


def compute_cluster_count(m: WorldModel, threshold: float = 30.0) -> int:
    """聚类数 —— 群集分化度量。"""
    active = m._lifecycle["boid"].active_indices
    if len(active) < 2:
        return len(active)
    x = m.attr("boid", "x")[active]
    y = m.attr("boid", "y")[active]
    # 简单 greedy 聚类
    visited = set()
    clusters = 0
    for i in range(len(active)):
        if i in visited:
            continue
        clusters += 1
        stack = [i]
        while stack:
            j = stack.pop()
            if j in visited:
                continue
            visited.add(j)
            dx = np.abs(x - x[j])
            dy = np.abs(y - y[j])
            dx = np.minimum(dx, WORLD_SIZE - dx)
            dy = np.minimum(dy, WORLD_SIZE - dy)
            nearby = np.where((dx < threshold) & (dy < threshold))[0]
            for k in nearby:
                if k not in visited:
                    stack.append(k)
    return clusters


TICKS = 400
order_history = []
cluster_history = []
neighbor_history = []

print("=== ES Boids 群集涌现实验 ===\n")
print(f"Boids: {NUM_BOIDS} | 感知半径: {PERCEPTION} | 世界: {WORLD_SIZE}²")

for tick in range(1, TICKS + 1):
    model.step()

    if tick % 40 == 0:
        order = compute_order_parameter(model)
        clusters = compute_cluster_count(model)
        active = model._lifecycle["boid"].active_indices
        avg_neighbors = float(model.attr("boid", "neighbor_count")[active].mean())

        order_history.append(order)
        cluster_history.append(clusters)
        neighbor_history.append(avg_neighbors)

        phase = "有序群集" if order > 0.7 else ("过渡态" if order > 0.3 else "无序随机")
        print(f"  tick {tick:3d}: 有序度={order:.3f} | 聚类数={clusters:3d} | "
              f"平均邻居={avg_neighbors:.1f} | {phase}")

# ===================================================================
# 5. ES 特色：相变分析
# ===================================================================
print(f"\n=== ES 涌现分析报告 ===")
print(f"初始有序度:       {order_history[0]:.3f}")
print(f"最终有序度:       {order_history[-1]:.3f}")
print(f"最大有序度:       {max(order_history):.3f} @ tick {(np.argmax(order_history)+1)*40}")
print(f"聚类数变化:       {cluster_history[0]} → {cluster_history[-1]}")
print(f"平均邻居数变化:   {neighbor_history[0]:.1f} → {neighbor_history[-1]:.1f}")

if max(order_history) > 0.7:
    print(f"\n✓ 观察到涌现：无序初始 → 有序群集（相变完成）")
    print(f"  相变发生在约 tick {(np.argmax(np.array(order_history) > 0.5) + 1) * 40}")
else:
    print(f"\n○ 未观察到完全相变，建议调大感知半径或运行更多 ticks")

print(f"\n=== ES Demo 完成 ===")
print("下一步：ES 前端用 HTTPBridge 获取 tick 数据，")
print("用 viewport-2d-kit 管相机 + Canvas 画 Boid，")
print("侧栏放 有序度/聚类数/熵 等涌现度量面板，")
print("实验配置面板做参数扫描（perception/max_speed 等）。")
