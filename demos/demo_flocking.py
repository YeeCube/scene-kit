"""Boids 群集 v0.2.0 —— WorldPlugin 封装 + BehaviorRegistry。

100 birds, 50 ticks. 展示 Plugin 系统与内置行为.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind, WorldPlugin

class FlockingPlugin(WorldPlugin):
    name = "flocking"
    def register_kinds(self, w):
        w.register_kind(EntityKind("bird", geometry="point",
            tags={"vx": np.float32, "vy": np.float32}))
    def register_behaviors(self, w):
        w.behaviors.flocking("bird", separation=1.5, alignment=1.0,
                             cohesion=1.0, radius=5.0, max_speed=2.0)
    def register_resources(self, w):
        w.add_resource({"size": 200, "n_birds": 100})

model = WorldModel(seed=42)
model.add_root_surface(200, 200)
model.add_plugin(FlockingPlugin())
cfg = model.get_resource(dict)

angles = np.random.uniform(0, 2*np.pi, cfg["n_birds"])
model.spawn("bird", n=cfg["n_birds"],
    u=np.random.uniform(0, cfg["size"], cfg["n_birds"]),
    v=np.random.uniform(0, cfg["size"], cfg["n_birds"]),
    vx=np.cos(angles)*2.0, vy=np.sin(angles)*2.0, r=60, g=180, b=220)

print("=== Boids 群集 v0.2.0 ===\n")
print(f"plugin: {FlockingPlugin.name}, birds: {cfg['n_birds']}")
print(f"kinds: {model.list_kinds()}")

model.run(50)
vm = model.export_viewmodel(format="dict")
print(f"\n50 ticks: {model._lifecycle['bird'].active_count} birds active")
print(f"ViewModel: {len(vm['agents'])} agents")
print("Done.")
