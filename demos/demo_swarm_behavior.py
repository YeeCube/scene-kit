"""群体行为仿真 v0.2.0 —— Boids 三规则 + DataCollector + 自定义指标.

120 个 agent, 400 ticks. 展示 tags 系统与涌现度量.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind

SIZE, N_BOIDS, RADIUS, MAX_V = 200, 120, 50.0, 4.0

model = WorldModel(seed=42)
model.add_root_surface(SIZE, SIZE, boundary_u="toroidal", boundary_v="toroidal")

boid = EntityKind("boid", geometry="point",
    tags={"vx": np.float32, "vy": np.float32, "energy": np.float32, "n_neighbors": np.int32})
model.register_kind(boid)

angles = np.random.uniform(0, 2*np.pi, N_BOIDS)
model.spawn("boid", n=N_BOIDS,
    u=np.random.uniform(0, SIZE, N_BOIDS), v=np.random.uniform(0, SIZE, N_BOIDS),
    vx=np.cos(angles)*3.0, vy=np.sin(angles)*3.0, energy=50.0,
    n_neighbors=np.zeros(N_BOIDS, dtype=np.int32), r=60, g=160, b=220)

@model.step_for("boid")
def boid_step(m, ids):
    u = m.attr("boid","u")[ids].astype(np.float64)
    v = m.attr("boid","v")[ids].astype(np.float64)
    vx = m.attr("boid","vx")[ids].astype(np.float64)
    vy = m.attr("boid","vy")[ids].astype(np.float64)
    n = len(ids)
    nvx, nvy = vx.copy(), vy.copy()
    for i in range(n):
        du, dv = u - u[i], v - v[i]
        du = np.where(du > SIZE/2, du - SIZE, np.where(du < -SIZE/2, du + SIZE, du))
        dv = np.where(dv > SIZE/2, dv - SIZE, np.where(dv < -SIZE/2, dv + SIZE, dv))
        d = np.sqrt(du**2 + dv**2)
        nb = (d > 0) & (d < RADIUS)
        m.set_attr("boid", "n_neighbors", np.array([ids[i]]), nb.sum())
        if nb.sum() < 2: continue
        close = d[nb] < RADIUS * 0.25
        if close.any():
            cdu, cdv = du[nb][close], dv[nb][close]
            cd = d[nb][close] + 1e-6
            nvx[i] += (-cdu / cd).mean() * 2.5
            nvy[i] += (-cdv / cd).mean() * 2.5
        nvx[i] += (vx[nb].mean() - vx[i]) * 0.4
        nvy[i] += (vy[nb].mean() - vy[i]) * 0.4
    sp = np.sqrt(nvx**2 + nvy**2); mk = sp > MAX_V
    nvx[mk] *= MAX_V / sp[mk]; nvy[mk] *= MAX_V / sp[mk]
    m.set_attr("boid", "vx", ids, nvx.astype(np.float32))
    m.set_attr("boid", "vy", ids, nvy.astype(np.float32))
    m.move("boid", ids, np.column_stack([nvx.astype(np.float32), nvy.astype(np.float32)]))
    m.wrap_toroidal("boid", ids)

def alignment_order(m):
    a = m._lifecycle["boid"].active_indices
    if len(a) == 0: return 0.0
    vx = m.attr("boid","vx")[a]; vy = m.attr("boid","vy")[a]
    sp = np.sqrt(vx**2 + vy**2)
    if sp.sum() == 0: return 0.0
    return float(np.sqrt((vx/(sp+1e-6)).mean()**2 + (vy/(sp+1e-6)).mean()**2))

model.collector.aggregate("boid", "vx", ["mean", "std"])
model.collector.add_metric("alignment", alignment_order)

print("=== 群体行为 v0.2.0 ===\n")
for tick in range(1, 201):
    model.step()
    if tick % 40 == 0:
        o = alignment_order(model)
        print(f"  tick {tick:3d}: 对齐度={o:.3f} {'有序' if o>0.7 else '过渡' if o>0.3 else '随机'}")

vm = model.export_viewmodel(format="dict")
print(f"\nViewModel: {len(vm['agents'])} agents")
print("Done.")
