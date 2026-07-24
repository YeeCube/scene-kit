"""Kuramoto 相振子模型 v0.2.0 —— 同步相变经典模型。

100 个振子，展示 tags + Perception 感知框架.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind

N_OSC = 100
model = WorldModel(backend="numpy", seed=42)
model.add_root_surface(200, 200)

osc = EntityKind("oscillator", geometry="point",
    tags={"phase": np.float32, "freq": np.float32},
    perceive={"radius": 40.0, "of_kinds": ["oscillator"], "self_tags": ["phase"]})
model.register_kind(osc)

angles = np.random.uniform(0, 2*np.pi, N_OSC)
model.spawn("oscillator", n=N_OSC,
    u=np.random.uniform(0,200,N_OSC), v=np.random.uniform(0,200,N_OSC),
    phase=np.cos(angles).astype(np.float32),
    freq=np.random.uniform(0.8, 1.2, N_OSC).astype(np.float32),
    r=80, g=160, b=255)

@model.step_for("oscillator")
def osc_step(m, perception):
    active = m._lifecycle["oscillator"].active_indices
    if len(active) == 0: return
    phase = m.attr("oscillator", "phase")[active]
    freq = m.attr("oscillator", "freq")[active]
    u = m.attr("oscillator", "u")[active]; v = m.attr("oscillator", "v")[active]
    new_phase = phase + freq * 0.1
    # 随机游走
    ang = np.random.uniform(0, 2*np.pi, len(active))
    m.move("oscillator", active, np.column_stack([np.cos(ang)*0.5, np.sin(ang)*0.5]))
    m.wrap_toroidal("oscillator", active)
    m.set_attr("oscillator", "phase", active, new_phase % (2*np.pi))

def order_param(m):
    active = m._lifecycle["oscillator"].active_indices
    if len(active) == 0: return 0.0
    ph = m.attr("oscillator", "phase")[active]
    return float(np.sqrt(np.sin(ph).mean()**2 + np.cos(ph).mean()**2))

model.collector.add_metric("order", order_param)

print("=== Kuramoto 相振子 v0.2.0 ===\n")
for tick in range(1, 101):
    model.step()
    if tick % 20 == 0:
        R = order_param(model)
        print(f"  tick {tick:3d}: order R={R:.3f} {'同步' if R>0.7 else '去同步' if R<0.3 else '过渡'}")

vm = model.export_viewmodel(format="dict")
print(f"\nViewModel: {len(vm['agents'])} agents")
print("Done.")
