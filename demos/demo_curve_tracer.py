"""曲线追踪 v0.2.0 —— 动点沿数学曲线运动 + 切线/法线计算.

展示 geometry point + tags 的数学可视化用法. 使用 Lissajous 曲线.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind

SIZE, C = 12.0, 6.0

def curve(t):
    """Lissajous-like parametric curve. x = 5*sin(2t), y = 5*cos(3t)"""
    return 5*np.sin(2*t), 5*np.cos(3*t)

def tangent(t):
    """dx/dt, dy/dt"""
    return 10*np.cos(2*t), -15*np.sin(3*t)

model = WorldModel(seed=0)
model.add_root_surface(SIZE, SIZE)

model.register_kind(EntityKind("tracer", geometry="point",
    tags={"t": np.float32,
          "tan_x": np.float32, "tan_y": np.float32,
          "norm_x": np.float32, "norm_y": np.float32}))
model.register_kind(EntityKind("trail", geometry="point", tags={}))
model.register_kind(EntityKind("axis", geometry="point", tags={}))

# 曲线采样点 (trail)
ts = np.linspace(0, 2*np.pi, 300)
cx, cy = curve(ts)
model.spawn("trail", n=300, u=cx + C, v=C - cy, r=100, g=180, b=255)

# 坐标轴
ax = np.linspace(-6, 6, 40)
model.spawn("axis", n=40, u=ax + C, v=np.full(40, C), r=150, g=150, b=150)
model.spawn("axis", n=40, u=np.full(40, C), v=C - ax, r=150, g=150, b=150)

# 动点
t0 = 0.0; px, py = curve(t0)
tx, ty = tangent(t0); tl = np.sqrt(tx**2 + ty**2)
pid = model.spawn("tracer", n=1, u=px + C, v=C - py, t=t0,
    tan_x=tx/tl, tan_y=-ty/tl, norm_x=ty/tl, norm_y=tx/tl, r=255, g=80, b=80)[0]

@model.step_for("tracer")
def tracer_step(m, ids):
    t = m.attr("tracer","t")[ids]; nt = (t + 0.08) % (2*np.pi)
    px2, py2 = curve(nt); tx2, ty2 = tangent(nt); tl2 = np.sqrt(tx2**2 + ty2**2)
    m.move_to("tracer", ids, px2 + C, C - py2)
    m.set_attr("tracer", "t", ids, nt)
    m.set_attr("tracer", "tan_x", ids, tx2/tl2)
    m.set_attr("tracer", "tan_y", ids, -ty2/tl2)
    m.set_attr("tracer", "norm_x", ids, ty2/tl2)
    m.set_attr("tracer", "norm_y", ids, tx2/tl2)

@model.step_for("trail")
def trail_step(m, ids): pass

@model.step_for("axis")
def axis_step(m, ids): pass

print("=== 曲线追踪 v0.2.0 ===\n")
for tick in range(1, 81):
    model.step()
    if tick % 10 == 0:
        tv = float(model.attr("tracer","t")[pid])
        tx_v = float(model.attr("tracer","tan_x")[pid])
        ty_v = float(model.attr("tracer","tan_y")[pid])
        print(f"  tick {tick:2d}: t={tv:.2f} 切线=({tx_v:+.3f},{ty_v:+.3f})")

vm = model.export_viewmodel(format="dict")
print(f"\nViewModel: {len(vm['agents'])} agents")
print("Done.")
