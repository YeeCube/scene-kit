"""多人追逐游戏 v0.2.0 —— WorldPlugin + PhaseScheduler + tags.

5 chasers vs 8 runners, 展示 Plugin 封装与回合制调度.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind, WorldPlugin
from world_model_kit.schedule import PhaseScheduler

class ChaseGamePlugin(WorldPlugin):
    name = "chase_game"
    def register_kinds(self, w):
        w.register_kind(EntityKind("chaser", geometry="point",
            tags={"vx": np.float32, "vy": np.float32, "score": np.int32, "team": np.int32}))
        w.register_kind(EntityKind("runner", geometry="point",
            tags={"vx": np.float32, "vy": np.float32, "stamina": np.float32,
                  "survival_time": np.int32, "team": np.int32}))
        w.register_kind(EntityKind("barrier", geometry="point",
            tags={"radius": np.float32, "team": np.int32}))

    def register_behaviors(self, w):
        CATCH_R = 5.0
        @w.step_for("chaser")
        def chaser_step(m, ids):
            ra = m._lifecycle["runner"].active_indices
            if len(ra) == 0: return
            cu, cv = m.attr("chaser","u")[ids], m.attr("chaser","v")[ids]
            ru, rv = m.attr("runner","u")[ra], m.attr("runner","v")[ra]
            for i, cid in enumerate(ids):
                d = np.sqrt((ru-cu[i])**2 + (rv-cv[i])**2); nj = np.argmin(d)
                if d[nj] <= CATCH_R:
                    m.kill("runner", np.array([ra[nj]]))
                    m.set_attr("chaser", "score", np.array([cid]),
                               m.attr("chaser","score")[cid] + 1)
                else:
                    m.move_toward("chaser", np.array([cid]),
                        float(ru[nj]), float(rv[nj]), max_distance=2.5)
            m.clamp_to_world("chaser", ids)

        @w.step_for("runner")
        def runner_step(m, ids):
            ca = m._lifecycle["chaser"].active_indices
            if len(ca) == 0: return
            cu, cv = m.attr("chaser","u")[ca], m.attr("chaser","v")[ca]
            ru, rv = m.attr("runner","u")[ids], m.attr("runner","v")[ids]
            for i, rid in enumerate(ids):
                d = np.sqrt((cu-ru[i])**2 + (cv-rv[i])**2); nj = np.argmin(d)
                dx, dy = ru[i]-cu[nj], rv[i]-cv[nj]
                dm = max(d[nj], 1e-6)
                m.move("runner", np.array([rid]), np.array([[dx/dm*1.8, dy/dm*1.8]]))
            m.set_attr("runner", "survival_time", ids,
                       m.attr("runner","survival_time")[ids] + 1)
            m.clamp_to_world("runner", ids)

        @w.step_for("barrier")
        def barrier_step(m, ids): pass

    def register_resources(self, w):
        w.add_resource({"game_ticks": 80, "catch_radius": 5.0})

model = WorldModel(seed=2026)
model.add_root_surface(120, 120)
model.add_plugin(ChaseGamePlugin())
cfg = model.get_resource(dict)

N_C, N_R = 5, 8
model.spawn("chaser", n=N_C,
    u=np.random.uniform(10, 40, N_C), v=np.random.uniform(10, 110, N_C),
    score=0, team=0, r=30, g=100, b=220)
model.spawn("runner", n=N_R,
    u=np.random.uniform(80, 110, N_R), v=np.random.uniform(10, 110, N_R),
    stamina=np.random.uniform(80, 120, N_R).astype(np.float32),
    survival_time=0, team=1, r=220, g=50, b=50)
model.spawn("barrier", n=5,
    u=np.random.uniform(30, 90, 5), v=np.random.uniform(30, 90, 5),
    radius=np.random.uniform(4, 8, 5).astype(np.float32), team=-1, r=100, g=100, b=100)

print("=== 追逐游戏 v0.2.0 ===\n")
for tick in range(1, cfg["game_ticks"]+1):
    model.step()
    ra = model._lifecycle["runner"].active_count
    if tick % 20 == 0 or ra == 0:
        scores = model.attr("chaser","score")[model._lifecycle["chaser"].active_indices]
        print(f"  tick {tick:3d}: runners={ra}, total catches={scores.sum()}")
    if ra == 0: break

scores = model.attr("chaser","score")[model._lifecycle["chaser"].active_indices]
print(f"\ncatches: {scores.sum()}/{N_R}, top chaser score={scores.max()}")
vm = model.export_viewmodel(format="dict")
print(f"ViewModel: {len(vm['agents'])} agents")
print("Done.")
