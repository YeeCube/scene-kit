"""Predator-Prey 模型 v0.2.0 —— 经典 Lotka-Volterra 种群动力学.

300 prey + 15 predator, 200 ticks. 最基本的 WMK 用法演示.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind

model = WorldModel(backend="numpy", seed=42)
model.add_root_surface(200, 200)

prey = EntityKind("prey", geometry="point",
    tags={"energy": np.float32, "vx": np.float32, "vy": np.float32})
predator = EntityKind("predator", geometry="point",
    tags={"energy": np.float32, "vx": np.float32, "vy": np.float32})
model.register_kind(prey)
model.register_kind(predator)

N_PREY, N_PREDATOR = 300, 15
model.spawn("prey", n=N_PREY,
    u=np.random.uniform(0, 200, N_PREY), v=np.random.uniform(0, 200, N_PREY),
    vx=np.random.uniform(-1, 1, N_PREY), vy=np.random.uniform(-1, 1, N_PREY),
    energy=50.0, r=0, g=200, b=0)
model.spawn("predator", n=N_PREDATOR,
    u=np.random.uniform(0, 200, N_PREDATOR), v=np.random.uniform(0, 200, N_PREDATOR),
    vx=0.0, vy=0.0, energy=100.0, r=220, g=30, b=30)

@model.step_for("prey")
def prey_step(m, ids):
    angle = np.random.uniform(0, 2*np.pi, len(ids))
    m.move("prey", ids, np.column_stack([np.cos(angle)*1.5, np.sin(angle)*1.5]))
    m.clamp_to_world("prey", ids)

@model.step_for("predator")
def predator_step(m, ids):
    pa = m._lifecycle["prey"].active_indices
    if len(pa) == 0: return
    pu = m.attr("prey","u")[pa]; pv = m.attr("prey","v")[pa]
    m.move_toward("predator", ids, float(pu.mean()), float(pv.mean()), max_distance=2.5)
    m.clamp_to_world("predator", ids)
    pdu, pdv = m.attr("predator","u")[ids], m.attr("predator","v")[ids]
    for i, pid in enumerate(ids):
        nb = m.within_radius("prey", pa, cx=pdu[i], cy=pdv[i], radius=3.0)
        if len(nb) > 0: m.kill("prey", nb[:1])

model.run(200)
fp = model._lifecycle["prey"].active_count
fpr = model._lifecycle["predator"].active_count
print(f"prey: {N_PREY} -> {fp} ({fp/N_PREY*100:.0f}%), predator: {N_PREDATOR} -> {fpr}")
vm = model.export_viewmodel(format="dict")
print(f"ViewModel: {len(vm['agents'])} agents")
print("Done.")
