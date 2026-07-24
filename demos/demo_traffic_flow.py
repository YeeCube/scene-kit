"""交通流仿真 v0.2.0 —— 双车道高速公路 + 换道行为.

80 辆车在 500m 直路上，展示 DataCollector + wrap_toroidal.
"""
import numpy as np
from world_model_kit import WorldModel, EntityKind

ROAD_LEN, N_CARS, SPEED_LIMIT = 500.0, 80, 12.0

model = WorldModel(backend="numpy", seed=2026)
model.add_root_surface(ROAD_LEN, 4, boundary_u="toroidal", boundary_v="clamp")

car = EntityKind("car", geometry="point",
    tags={"speed": np.float32, "pref_speed": np.float32, "lane": np.int32})
model.register_kind(car)

pos = np.sort(np.random.uniform(0, ROAD_LEN, N_CARS))
sp = np.random.uniform(0.5, 1.0, N_CARS) * SPEED_LIMIT
model.spawn("car", n=N_CARS, u=pos,
    v=np.where(np.random.random(N_CARS) < 0.6, 1.0, 3.0).astype(np.float32),
    speed=sp, pref_speed=sp, lane=np.where(np.random.random(N_CARS) < 0.6, 0, 1).astype(np.int32),
    r=50, g=120, b=220)

@model.step_for("car")
def car_step(m, ids):
    u = m.attr("car", "u")[ids]; v = m.attr("car", "speed")[ids]
    v0 = m.attr("car", "pref_speed")[ids]; lane = m.attr("car", "lane")[ids]
    n = len(ids)
    # 按位置排序后计算车头距
    si = np.argsort(u)
    su, sv, sv0, sl = u[si], v[si], v0[si], lane[si]
    new_v = sv.copy()
    for i in range(n):
        j = (i+1) % n
        gap = su[j] - su[i]
        if gap <= 0: gap += ROAD_LEN
        # 同车道跟驰
        if sl[i] == sl[j] and gap < 20:
            new_v[i] = max(1.0, sv[i] - 3.0 * (1 - gap/20))
        else:
            new_v[i] = min(SPEED_LIMIT, sv[i] + 1.5 * (sv0[i] - sv[i]) / sv0[i])
            # 慢车换道
            if sv[i] < 4 and np.random.random() < 0.2:
                sl[i] = 1 - sl[i]
    isi = np.argsort(si)
    m.set_attr("car", "speed", ids, new_v[isi])
    m.set_attr("car", "lane", ids, sl[isi])
    m.move("car", ids, np.column_stack([new_v[isi], np.zeros(n, dtype=np.float32)]))
    m.wrap_toroidal("car", ids)

model.collector.collect("car", ["speed"])
model.collector.aggregate("car", "speed", ["mean", "std", "min", "max"])

print("=== 交通流 v0.2.0 ===\n")
for tick in range(1, 151):
    model.step()
    if tick % 30 == 0:
        a = model._lifecycle["car"].active_indices
        ms = float(model.attr("car", "speed")[a].mean())
        print(f"  tick {tick:3d}: 均速={ms:.1f} m/s")

vm = model.export_viewmodel(format="dict")
print(f"\nViewModel: {len(vm['agents'])} agents")
print("Done.")
