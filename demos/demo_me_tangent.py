"""ME 数学引擎集成 Demo —— 切线/法线动态演示。

演示 ME 如何使用 world-model-kit 作为数学可视化后端：

下游链路：world-model-kit → MathEngine → matheshop IDE → MathExplorer 研究

ME 的特殊需求：
- 曲线对象（数学函数 → 离散采样点 → Curve）
- 动点嵌入曲线（参数 t 沿曲线运动）
- 几何计算（切线方向、法线方向、曲率）
- 向量渲染（切向量箭头、法向量箭头、标注文本）
- 参数实时调节（t 的滑块控制 → 动点位置变化）

用法::

    python demos/demo_me_tangent.py
"""

import numpy as np
from world_model_kit import WorldModel, EntityKind

# ===================================================================
# 1. ME 特色：数学函数 → 曲线对象
# ===================================================================
WORLD_SIZE = 12.0   # 数学坐标系 [-6, 6] × [-6, 6]
CENTER = WORLD_SIZE / 2  # 世界坐标偏移（数学原点 → 世界中心）

def math_to_world(mx, my):
    """数学坐标 → 世界坐标。"""
    return mx + CENTER, CENTER - my  # y 翻转

def f(x):
    """目标函数：y = sin(x) + 0.3*cos(3x)。"""
    return np.sin(x) + 0.3 * np.cos(3 * x)

def f_prime(x):
    """导数：f'(x) = cos(x) - 0.9*sin(3x)。"""
    return np.cos(x) - 0.9 * np.sin(3 * x)

# ===================================================================
# 2. ME 特色：EntityKind for 数学对象
# ===================================================================
model = WorldModel(world_width=WORLD_SIZE, world_height=WORLD_SIZE, seed=0)

# 动点——嵌入在曲线上的实数
point_kind = EntityKind("point",
    position=True,
    color=True, size=True,
    custom={
        "t": np.float32,            # 参数 t（沿曲线的位置）
        "tangent_dx": np.float32,   # 切线方向 x
        "tangent_dy": np.float32,   # 切线方向 y
        "normal_dx": np.float32,    # 法线方向 x
        "normal_dy": np.float32,    # 法线方向 y
        "curvature": np.float32,    # 曲率
    },
)
model.register_kind(point_kind)

# 曲线采样点——当作静态 Agent 存储
curve_kind = EntityKind("curve_sample",
    position=True,
    color=True, size=True,
)
model.register_kind(curve_kind)

# 轴——当作静态 Agent 存储
axis_kind = EntityKind("axis",
    position=True,
    color=True, size=True,
)
model.register_kind(axis_kind)

# ===================================================================
# 3. ME 特色：生成曲线采样点 + 坐标轴
# ===================================================================
# 曲线采样
N_SAMPLES = 200
xs = np.linspace(-6, 6, N_SAMPLES)
ys = f(xs)
wx, wy = math_to_world(xs, ys)
model.spawn("curve_sample", n=N_SAMPLES,
    x=wx, y=wy, r=100, g=180, b=255, size=1.5,
)

# X 轴
ax = np.linspace(-6, 6, 50)
model.spawn("axis", n=50,
    x=ax + CENTER, y=np.full(50, CENTER), r=150, g=150, b=150, size=1.0,
)
# Y 轴
ay = np.linspace(-6, 6, 50)
model.spawn("axis", n=50,
    x=np.full(50, CENTER), y=CENTER - ay, r=150, g=150, b=150, size=1.0,
)

# ===================================================================
# 4. ME 特色：动点沿曲线运动
# ===================================================================
t0 = -4.0  # 初始参数
px0, py0 = math_to_world(t0, f(t0))
fp0 = f_prime(t0)

# 切线方向（单位向量）
tangent_len = np.sqrt(1 + fp0**2)
tx = 1.0 / tangent_len
ty = -fp0 / tangent_len  # y 翻转

# 法线方向（切线逆时针 90°）
nx = -ty
ny = tx

point_id = model.spawn("point", n=1,
    x=px0, y=py0, t=t0,
    tangent_dx=tx, tangent_dy=ty,
    normal_dx=nx, normal_dy=ny,
    curvature=0.0, r=255, g=80, b=80, size=4.0,
)[0]

# ===================================================================
# 5. ME 特色：step_for 更新动点 + 几何计算
# ===================================================================
@model.step_for("point")
def point_step(m, ids):
    """每个 tick：沿曲线移动动点，重新计算切向量和法向量。

    这是 MathEngine 的后端核心——数学计算在 Python 完成，
    前端（matheshop IDE）只负责渲染箭头和标注。
    """
    t = m.attr("point", "t")[ids]
    new_t = t + 0.15  # 参数增量

    # 周期性环绕
    new_t = np.where(new_t > 6, -6 + (new_t - 6), new_t)

    mx = new_t
    my = f(new_t)
    wx, wy = math_to_world(mx, my)

    # 切线方向
    fp = f_prime(new_t)
    t_len = np.sqrt(1 + fp**2)
    tx = 1.0 / t_len
    ty = -fp / t_len

    # 法线方向
    nx = -ty
    ny = tx

    # 曲率 (简化)
    fpp = -np.sin(new_t) - 2.7 * np.cos(3 * new_t)  # f''(x)
    curvature = np.abs(fpp) / (1 + fp**2)**1.5

    m.move_to("point", ids, wx, wy)
    m.set_attr("point", "t", ids, new_t)
    m.set_attr("point", "tangent_dx", ids, tx)
    m.set_attr("point", "tangent_dy", ids, ty)
    m.set_attr("point", "normal_dx", ids, nx)
    m.set_attr("point", "normal_dy", ids, ny)
    m.set_attr("point", "curvature", ids, curvature)

    # ME 特有：在关键点自动放慢（曲率大的地方慢慢过）
    # 前端通过 viewport-2d-kit 的 animateCamera 跟随动点


@model.step_for("curve_sample")
def noop(m, ids):
    pass

@model.step_for("axis")
def noop2(m, ids):
    pass

# ===================================================================
# 6. 运行 + 输出几何数据
# ===================================================================
TICKS = 80

print("=== ME 切线/法线动态演示 ===\n")
print(f"函数: y = sin(x) + 0.3×cos(3x), x ∈ [-6, 6]")
print(f"曲线采样点: {N_SAMPLES} | 动点初始位置: t = {t0}")
print(f"运行 {TICKS} ticks...\n")

snapshots = []
for tick in range(1, TICKS + 1):
    model.step()

    if tick % 10 == 0:
        t_val = float(model.attr("point", "t")[point_id])
        tx = float(model.attr("point", "tangent_dx")[point_id])
        ty = float(model.attr("point", "tangent_dy")[point_id])
        curv = float(model.attr("point", "curvature")[point_id])

        snapshots.append((tick, t_val, tx, ty, curv))
        print(f"  tick {tick:2d}: t={t_val:+.3f} | "
              f"切向量=({tx:+.3f}, {ty:+.3f}) | 曲率={curv:.3f}")

# ===================================================================
# 7. ME 特色：输出几何数据供前端渲染
# ===================================================================
print(f"\n=== ME 几何数据导出 ===")
print("供 matheshop IDE 前端消费的 ViewModel 示例:")

vm = {
    "tick": model.tick,
    "world_width": WORLD_SIZE,
    "world_height": WORLD_SIZE,
    "curve": {
        "name": "y = sin(x) + 0.3×cos(3x)",
        "sample_points": [
            {"x": float(model.attr("curve_sample", "x")[i]),
             "y": float(model.attr("curve_sample", "y")[i])}
            for i in range(0, N_SAMPLES, 20)  # 稀疏采样给前端
        ],
    },
    "point": {
        "id": int(point_id),
        "x": float(model.attr("point", "x")[point_id]),
        "y": float(model.attr("point", "y")[point_id]),
        "t": float(model.attr("point", "t")[point_id]),
        "tangent": {
            "dx": float(model.attr("point", "tangent_dx")[point_id]),
            "dy": float(model.attr("point", "tangent_dy")[point_id]),
        },
        "normal": {
            "dx": float(model.attr("point", "normal_dx")[point_id]),
            "dy": float(model.attr("point", "normal_dy")[point_id]),
        },
        "curvature": float(model.attr("point", "curvature")[point_id]),
    },
}  # close vm dict
# annotations 需要引用 vm，所以分开构建
vm["annotations"] = [
    {"type": "tangent_label", "text": "T⃗", "at_t": vm["point"]["t"]},
    {"type": "normal_label", "text": "N⃗", "at_t": vm["point"]["t"]},
]
print("  curve samples:", len(vm["curve"]["sample_points"]), "points")
print("  point: t =", f'{vm["point"]["t"]:.3f}')
print("  tangent:", f'({vm["point"]["tangent"]["dx"]:.3f}, {vm["point"]["tangent"]["dy"]:.3f})')
print("  curvature:", f'{vm["point"]["curvature"]:.4f}')

print(f"\n=== ME Demo 完成 ===")
print("下一步：MathEngine 消费 world-model-kit ViewModel，")
print("做更复杂的数学计算（梯度场 Agent / 流线 / 曲面交线），")
print("matheshop IDE 前端用 viewport-2d-kit 管相机 + Canvas 画:")
print("  - 曲线：蓝色折线")
print("  - 动点：红色实心圆 + 拖拽交互")
print("  - 切向量：红色箭头（从动点沿切线方向延伸）")
print("  - 法向量：蓝色箭头（从动点沿法线方向延伸）")
print("  - LaTeX 标注：T⃗ / N⃗ / κ = ...")
print("  - 参数滑块：t ∈ [-6, 6] 实时调节")
print("MathExplorer 研究项目在此基础上做更高维的数学探索。")
