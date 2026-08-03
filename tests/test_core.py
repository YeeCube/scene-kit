"""world-model-kit v0.2.0 综合测试。"""
import numpy as np
import pytest
from world_model_kit import WorldModel, EntityKind, WorldPlugin
from world_model_kit.geometry import PointGeometry, SurfaceGeometry, VolumeGeometry
from world_model_kit.schedule import SequentialScheduler, RandomScheduler, PhaseScheduler

def _make_2d_model():
    m = WorldModel(seed=42)
    m.add_root_surface(200, 200)
    return m

class TestEntityKind:
    def test_point(self):
        k = EntityKind("test", geometry="point", tags={"energy": np.float32})
        assert k.geometry == "point"; assert k.dim == 0.0
        assert "energy" in k.tags; assert k.type == "AGENT"
    def test_surface(self):
        k = EntityKind("terrain", geometry="surface", dim=2.0, type="ENV")
        assert k.dim == 2.0; assert k.type == "ENV"
    def test_volume(self):
        k = EntityKind("space", geometry="volume"); assert k.dim == 3.0
    def test_invalid_geometry(self):
        with pytest.raises(ValueError): EntityKind("bad", geometry="invalid")
    def test_invalid_type(self):
        with pytest.raises(ValueError): EntityKind("bad", type="INVALID")
    def test_kind_to_dtypes_point(self):
        from world_model_kit.entity_kind import _kind_to_dtypes
        d = _kind_to_dtypes(EntityKind("p", geometry="point", tags={"energy": np.float32}))
        assert "u" in d and "v" in d and "energy" in d and "_parent_id" in d
        assert "mass" in d and "r" in d and "g" in d
    def test_kind_to_dtypes_volume(self):
        from world_model_kit.entity_kind import _kind_to_dtypes
        d = _kind_to_dtypes(EntityKind("v", geometry="volume"))
        assert "u" in d and "v" in d and "w" in d

class TestGeometry:
    def test_point_metric(self):
        g = PointGeometry(); d = g.metric(np.array([[0,0],[3,4]]), np.array([[0,0],[3,4]]))
        assert d.shape == (2,2); assert d[0,1] == pytest.approx(5.0)
    def test_point_move(self):
        g = PointGeometry(); new = g.move(np.array([[0,0],[10,20]],dtype=np.float32),
            np.array([[1,2],[3,4]],dtype=np.float32), dt=2.0)
        assert new[0,0]==2.0 and new[0,1]==4.0
    def test_surface_metric(self):
        g = SurfaceGeometry(100,100); d = g.metric(np.array([[0,0]]), np.array([[3,4]]))
        assert d[0,0]==pytest.approx(5.0)
    def test_surface_clamp(self):
        g=SurfaceGeometry(100,100);c=g.clamp(np.array([[110,-5]],dtype=np.float32))
        assert c[0,0]==100.0 and c[0,1]==0.0
    def test_surface_toroidal(self):
        g=SurfaceGeometry(100,100);w=g.wrap_toroidal(np.array([[110,-5]],dtype=np.float32))
        assert w[0,0]==10.0 and w[0,1]==95.0
    def test_volume_contains(self):
        g=VolumeGeometry(100,100,100)
        assert g.contains(np.array([[50,50,50]]))[0]; assert not g.contains(np.array([[150,50,50]]))[0]

class TestWorldModel:
    @pytest.fixture
    def m(self):
        m = WorldModel(seed=42); m.add_root_surface(200, 200)
        m.register_kind(EntityKind("test", geometry="point",
            tags={"energy": np.float32, "vx": np.float32, "vy": np.float32}))
        return m
    def test_init(self, m): assert "test" in m.list_kinds()
    def test_duplicate(self, m):
        with pytest.raises(Exception): m.register_kind(EntityKind("test", geometry="point"))
    def test_spawn(self, m):
        ids = m.spawn("test", n=10, u=np.random.uniform(0,200,10), v=np.random.uniform(0,200,10), energy=50.0)
        assert len(ids)==10 and m._lifecycle["test"].active_count==10
    def test_move(self, m):
        ids = m.spawn("test", n=3, u=[10,20,30], v=[10,20,30])
        m.move("test", ids, np.column_stack([[5.,5.,5.],[5.,5.,5.]]))
        assert np.allclose(m.attr("test","u")[ids], [15,25,35])
    def test_clamp(self, m):
        ids = m.spawn("test", n=1, u=250, v=-10); m.clamp_to_world("test", ids)
        assert m.attr("test","u")[ids[0]]<=200 and m.attr("test","v")[ids[0]]>=0
    def test_wrap(self, m):
        ids = m.spawn("test", n=1, u=250, v=-10); m.wrap_toroidal("test", ids)
        assert 0<=m.attr("test","u")[ids[0]]<=200
    def test_kill(self, m):
        ids=m.spawn("test",n=5,u=np.zeros(5),v=np.zeros(5));m.kill("test",ids[:2])
        assert m._lifecycle["test"].active_count==3
    def test_step_for(self, m):
        m.spawn("test",n=5,u=np.zeros(5),v=np.zeros(5))
        @m.step_for("test")
        def s(model,ids): model.move("test",ids,np.column_stack([np.ones(5),np.zeros(5)]))
        m.step(); assert m.tick==1
    def test_run(self, m):
        m.spawn("test",n=5,u=np.zeros(5),v=np.zeros(5))
        @m.step_for("test")
        def s(model,ids): pass
        m.run(10); assert m.tick==10

class TestTags:
    def test_kinds_with_tag(self):
        m = _make_2d_model()
        m.register_kind(EntityKind("a",geometry="point",tags={"energy":np.float32}))
        m.register_kind(EntityKind("b",geometry="point",tags={"energy":np.float32,"hp":np.float32}))
        m.register_kind(EntityKind("c",geometry="point",tags={"hp":np.float32}))
        assert set(m.kinds_with_tag("energy"))=={"a","b"}
        assert set(m.kinds_with_tag("hp"))=={"b","c"}
        assert m.kinds_with_tag("x")==[]
    def test_tagged(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point",tags={"energy":np.float32}))
        m.spawn("a",n=3,u=[1,2,3],v=[4,5,6])
        assert len(m.tagged("energy")["a"])==3
    def test_where(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point",tags={"energy":np.float32}))
        m.spawn("a",n=5,u=np.zeros(5),v=np.zeros(5),energy=[10,20,30,40,50])
        assert len(m.where("a","energy",lt=25))==2

class TestPlugin:
    def test_add_plugin(self):
        m=_make_2d_model()
        class TP(WorldPlugin):
            name="t"
            def register_kinds(self,w):w.register_kind(EntityKind("bird",geometry="point"))
            def register_resources(self,w):w.add_resource({"k":"v"})
        m.add_plugin(TP());assert "bird" in m.list_kinds();assert m.get_resource(dict)=={"k":"v"}

class TestDataCollector:
    def test_collect(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point",tags={"v":np.float32}))
        m.spawn("a",n=3,u=[1,2,3],v=[10,20,30]);m.collector.collect("a",["v"]);m.collector.aggregate("a","v",["mean"])
        @m.step_for("a")
        def s(model,ids):pass
        m.run(5);df=m.collector.export_dataframe()
        assert df.shape[0]==5 and "a.v.mean" in df.columns
    def test_metric(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point"))
        m.spawn("a",n=5,u=np.zeros(5),v=np.zeros(5));m.collector.add_metric("count",lambda m:42.0)
        @m.step_for("a")
        def s(model,ids):pass
        m.run(3);df=m.collector.export_dataframe();assert "metric.count" in df.columns

class TestViewModel:
    def test_dict(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point"))
        m.spawn("a",n=5,u=np.random.uniform(0,100,5),v=np.random.uniform(0,100,5),r=255,g=0,b=0)
        vm=m.export_viewmodel(format="dict")
        assert isinstance(vm,dict) and vm["tick"]==0 and len(vm["agents"])==5
    def test_json(self):
        m=_make_2d_model();m.register_kind(EntityKind("a",geometry="point"))
        m.spawn("a",n=3,u=[1,2,3],v=[4,5,6])
        import json;vm=json.loads(m.export_viewmodel(format="json"))
        assert len(vm["agents"])==3

class TestScheduler:
    def test_sequential(self):
        s=SequentialScheduler();m=_make_2d_model()
        m.register_kind(EntityKind("a",geometry="point"));m.register_kind(EntityKind("b",geometry="point"))
        assert s.get_step_order(m)==["a","b"]
    def test_random(self):
        s=RandomScheduler(seed=0);m=_make_2d_model()
        m.register_kind(EntityKind("a",geometry="point"));m.register_kind(EntityKind("b",geometry="point"))
        assert set(s.get_step_order(m))=={"a","b"}
    def test_phase(self):
        s=PhaseScheduler({"combat":["a","b"],"resolve":["c"]});m=_make_2d_model()
        m.register_kind(EntityKind("a",geometry="point"));m.register_kind(EntityKind("b",geometry="point"))
        m.register_kind(EntityKind("c",geometry="point"));
        assert s.get_step_order(m)==["a","b"];s.set_phase("resolve");assert s.get_step_order(m)==["c"]
