# Mock-based smoke test for KARUSELKA 1.0 (no Blender needed).
# Validates: module exec, register/unregister, pure helpers (bbox center,
# auto radius, end frame/angle), create rig (pivot/camera/constraint/
# keyframes + LINEAR), user-camera mode, repeat-create, marker-scoped
# removal, render operator.
import os
import sys
import types
import math
import traceback

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  OK " if cond else "FAIL ") + name + ((" -- " + detail) if detail and not cond else ""))


TAU = math.tau

# ---------------------------------------------------------------- mocks
class FakeVec:
    def __init__(self, xyz=(0.0, 0.0, 0.0)):
        if hasattr(xyz, "xyz"):
            xyz = xyz.xyz
        self.xyz = tuple(float(v) for v in xyz)

    @property
    def x(self):
        return self.xyz[0]

    @property
    def y(self):
        return self.xyz[1]

    @property
    def z(self):
        return self.xyz[2]

    def __iter__(self):
        return iter(self.xyz)

    def __len__(self):
        return 3

    def __getitem__(self, i):
        return self.xyz[i]

    def __add__(self, o):
        return FakeVec([a + b for a, b in zip(self.xyz, FakeVec(o).xyz)])

    __radd__ = __add__

    def __iadd__(self, o):
        self.xyz = tuple(a + b for a, b in zip(self.xyz, FakeVec(o).xyz))
        return self

    def __sub__(self, o):
        return FakeVec([a - b for a, b in zip(self.xyz, FakeVec(o).xyz)])

    def __mul__(self, s):
        return FakeVec([a * s for a in self.xyz])

    __rmul__ = __mul__

    def __truediv__(self, s):
        return FakeVec([a / s for a in self.xyz])

    def __itruediv__(self, s):
        self.xyz = tuple(a / s for a in self.xyz)
        return self

    def __repr__(self):
        return f"FakeVec{self.xyz}"


class FakeMatrix:
    """Translation-only 4x4: matrix @ vec == vec + translation."""

    def __init__(self, translation=(0.0, 0.0, 0.0)):
        self.t = FakeVec(translation)

    def __matmul__(self, vec):
        return FakeVec([a + b for a, b in zip(FakeVec(vec).xyz, self.t.xyz)])

    def copy(self):
        return FakeMatrix(self.t.xyz)


class FakeFCurve:
    def __init__(self, data_path, index):
        self.data_path = data_path
        self.index = index
        self.keyframe_points = []


class FakeFCurves(list):
    def _get_or_create(self, data_path, index):
        for fc in self:
            if fc.data_path == data_path and fc.index == index:
                return fc
        fc = FakeFCurve(data_path, index)
        self.append(fc)
        return fc

    def find(self, data_path, index=0):
        for fc in self:
            if fc.data_path == data_path and fc.index == index:
                return fc
        return None


class FakeConstraints(list):
    def new(self, ctype):
        con = types.SimpleNamespace(type=ctype,
                                    name={"TRACK_TO": "Track To"}.get(ctype, ctype),
                                    target=None,
                                    track_axis='TRACK_NEXT',
                                    up_axis='UP_Y',
                                    influence=1.0)
        self.append(con)
        return con

    def remove(self, con):
        list.remove(self, con)


class FakeObj:
    """Object with dict-style ID props (ob["key"]) like real Blender."""

    def __init__(self, otype, data=None, name="Object"):
        self.type = otype
        self.data = data
        self.name = name
        self._props = {}
        self._colls = []
        self.location = FakeVec()
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.matrix_world = FakeMatrix()
        self.bound_box = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                          (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
        self.dimensions = FakeVec((2.0, 2.0, 2.0))
        self.parent = None
        self.matrix_parent_inverse = FakeMatrix()
        self.constraints = FakeConstraints()
        self.empty_display_type = 'PLAIN_AXES'
        self._anim = None

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __contains__(self, key):
        return key in self._props

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value

    def __delitem__(self, key):
        del self._props[key]

    @property
    def animation_data(self):
        return self._anim

    def keyframe_insert(self, data_path, frame=0, index=-1):
        if self._anim is None:
            self._anim = types.SimpleNamespace(action=None)
            self._anim.action = types.SimpleNamespace(fcurves=FakeFCurves())
        fcurves = self._anim.action.fcurves
        for i in range(3):
            fc = fcurves._get_or_create(data_path, i)
            fc.keyframe_points.append(types.SimpleNamespace(
                co=(float(frame), self.rotation_euler[i]),
                interpolation='BEZIER'))


class FakeCamData:
    _obj_type = 'CAMERA'

    def __init__(self, name="Camera"):
        self.name = name
        self.lens = 50.0
        self.dof = types.SimpleNamespace(use_dof=False)


class FakeObjCollection:
    def __init__(self):
        self._items = {}

    def link(self, obj):
        self._items[obj.name] = obj
        obj._colls.append(self)

    def unlink(self, obj):
        self._items.pop(obj.name, None)

    def get(self, name):
        return self._items.get(name)

    def __iter__(self):
        return iter(list(self._items.values()))

    def __len__(self):
        return len(self._items)


class FakeSceneCollection:
    def __init__(self):
        self.objects = FakeObjCollection()


class FakeScene:
    def __init__(self):
        self.collection = FakeSceneCollection()
        self.frame_start = 1
        self.frame_end = 250
        self.frame_set_calls = []
        self.render = types.SimpleNamespace(filepath="/tmp/render/", fps=24)

    @property
    def objects(self):
        return list(self.collection.objects)

    def frame_set(self, frame):
        self.frame_set_calls.append(frame)


class FakeObjectsDB:
    def __init__(self):
        self._db = {}

    def new(self, name, object_data=None):
        otype = getattr(object_data, "_obj_type", None) or 'EMPTY'
        ob = FakeObj(otype, data=object_data, name=name)
        self._db[name] = ob
        return ob

    def get(self, name, default=None):
        return self._db.get(name, default)

    def remove(self, ob, do_unlink=False):
        # do_unlink kwarg is the classic mock trap — must be accepted
        self._db.pop(ob.name, None)
        for coll in list(ob._colls):
            coll.unlink(ob)

    def __len__(self):
        return len(self._db)

    def __iter__(self):
        return iter(list(self._db.values()))


db = FakeObjectsDB()

bpy = types.ModuleType("bpy")
bpy.__path__ = []  # package-style so "from bpy.props import ..." resolves
bpy.types = types.ModuleType("bpy.types")
# PropertyGroup supports self["key"] ID props on the instance
bpy.types.PropertyGroup = type("PropertyGroup", (), {
    "get": lambda self, k, d=None: getattr(self, "_idprops", {}).get(k, d),
    "__getitem__": lambda self, k: getattr(self, "_idprops", {})[k],
    "__setitem__": lambda self, k, v: (getattr(self, "_idprops", None) or self.__dict__.setdefault("_idprops", {})).__setitem__(k, v),
})
bpy.types.Panel = type("Panel", (), {})
bpy.types.Operator = type("Operator", (), {})
bpy.types.Scene = type("Scene", (), {})
bpy.types.Object = type("Object", (), {})

# prop factories return the declared default -> class attrs behave like real props
PROP_KW = {}


def _prop_factory():
    def f(**kw):
        PROP_KW[kw.get("name", "__anon_%d" % len(PROP_KW))] = kw
        return kw.get("default")
    return f


bpy.props = types.ModuleType("bpy.props")
bpy.props.StringProperty = _prop_factory()
bpy.props.IntProperty = _prop_factory()
bpy.props.BoolProperty = _prop_factory()
bpy.props.FloatProperty = _prop_factory()
bpy.props.EnumProperty = _prop_factory()

_registered = []
bpy.utils = types.ModuleType("bpy.utils")
bpy.utils.register_class = lambda cls: _registered.append(cls.__name__)
bpy.utils.unregister_class = lambda cls: _registered.remove(cls.__name__)

_pointers = []


def _pointer(**kw):
    PROP_KW[kw.get("name", "__pointer_%d" % len(_pointers))] = kw
    _pointers.append(kw.get("type"))
    return None


bpy.props.PointerProperty = _pointer

bpy.app = types.ModuleType("bpy.app")
mathutils = types.ModuleType("mathutils")
mathutils.Vector = FakeVec
mathutils.Matrix = FakeMatrix

render_calls = []
bpy.ops = types.SimpleNamespace(
    render=types.SimpleNamespace(
        render=lambda *a, **kw: render_calls.append((a, kw)) or {'FINISHED'}))

_scene = FakeScene()
bpy.data = types.SimpleNamespace(objects=db,
                                 cameras=types.SimpleNamespace(new=FakeCamData))
bpy.context = types.SimpleNamespace(scene=_scene, active_object=None)

for mod in (bpy, bpy.types, bpy.props, bpy.utils, bpy.app, mathutils):
    sys.modules[mod.__name__] = mod

# ---------------------------------------------------------------- exec module
path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "extension", "__init__.py")
src = open(path, encoding="utf-8").read()
ns = {"__name__": "karuselka_test", "__file__": path, "__package__": "karuselka_test"}
try:
    exec(compile(src, path, "exec"), ns)
    check("module exec without NameError", True)
except Exception:
    check("module exec without NameError", False, traceback.format_exc())
    sys.exit(1)

KR_SceneSettings = ns["KR_SceneSettings"]

# py3.14 (PEP 649): annotation expressions are lazy. Force evaluation and
# mirror what Blender's prop metaclass does on 3.11 — store the values as
# class attributes, so instances get the declared defaults.
_anns = KR_SceneSettings.__annotations__
for _name, _val in _anns.items():
    setattr(KR_SceneSettings, _name, _val)

# ---------------------------------------------------------------- register
try:
    ns["register"]()
    check("register() runs", True)
except Exception:
    check("register() runs", False, traceback.format_exc())
    sys.exit(1)

check("all classes registered", len(_registered) == len(ns["classes"]),
      f"{_registered} vs {len(ns['classes'])} classes")
check("Scene.karuselka pointer added", KR_SceneSettings in _pointers)
check("idname create_rig", ns["KR_OT_create_rig"].bl_idname == "karuselka.create_rig")
check("idname remove_rig", ns["KR_OT_remove_rig"].bl_idname == "karuselka.remove_rig")
check("idname render_turntable",
      ns["KR_OT_render_turntable"].bl_idname == "karuselka.render_turntable")
check("panel category KARUSELKA", ns["KR_PT_main_panel"].bl_category == "KARUSELKA")
_anns = KR_SceneSettings.__annotations__
check("direction default CW", _anns["direction"] == "CW")
check("direction has CW+CCW items",
      [i[0] for i in PROP_KW["Dir"]["items"]] == ["CW", "CCW"],
      str(PROP_KW.get("Dir"))[:200])
check("frames default 120", PROP_KW["Frames"]["default"] == 120)
check("output default //turntable/", PROP_KW["Output"]["default"] == "//turntable/")
check("camera poll filters CAMERA type",
      PROP_KW["Camera"].get("poll") is ns["_poll_camera"]
      and ns["_poll_camera"](None, types.SimpleNamespace(type='CAMERA'))
      and not ns["_poll_camera"](None, types.SimpleNamespace(type='MESH')))

# ---------------------------------------------------------------- scene glue
def fresh_props(target=None):
    props = KR_SceneSettings()
    _scene.karuselka = props
    if target is not None:
        props.target = target
    bpy.context.active_object = None
    return props


def make_target(name="Target", translation=(0.0, 0.0, 0.0)):
    ob = FakeObj('MESH', name=name)
    ob.matrix_world = FakeMatrix(translation)
    db._db[name] = ob
    _scene.collection.objects.link(ob)
    return ob


def reset():
    db._db.clear()
    _scene.collection.objects._items.clear()
    _scene.frame_start = 1
    _scene.frame_end = 250
    _scene.render.filepath = "/tmp/render/"
    render_calls.clear()
    bpy.context.active_object = None


def z_fcurve(ob):
    return ob.animation_data.action.fcurves.find("rotation_euler", index=2)


# ---------------------------------------------------------------- pure helpers
check("end frame 120x1.0 -> 120", ns["turn_end_frame"](120, 1.0) == 120)
check("end frame 120x1.5 -> 180", ns["turn_end_frame"](120, 1.5) == 180)
check("end frame tiny rounds -> min 2", ns["turn_end_frame"](2, 0.1) == 2)
check("angle CCW positive", ns["turn_end_angle"](1.0, 'CCW') == TAU)
check("angle CW negative", ns["turn_end_angle"](1.0, 'CW') == -TAU)
check("angle CW 2.5 rounds", ns["turn_end_angle"](2.5, 'CW') == -2.5 * TAU)

cube = FakeObj('MESH')
center = ns["bbox_center_world"](cube)
check("bbox center at origin",
      (center.x, center.y, center.z) == (0.0, 0.0, 0.0), str(center))
cube.matrix_world = FakeMatrix((5.0, 0.0, 2.0))
center = ns["bbox_center_world"](cube)
check("bbox center follows matrix", (center.x, center.y, center.z) == (5.0, 0.0, 2.0),
      str(center))

cube.dimensions = FakeVec((2.0, 2.0, 2.0))
check("auto radius 2m cube -> 3.0", ns["auto_radius"](cube) == 3.0)
cube.dimensions = FakeVec((1.0, 4.0, 2.0))
check("auto radius max dim", ns["auto_radius"](cube) == 6.0)
cube.dimensions = FakeVec((0.0, 0.0, 0.0))
check("auto radius zero dims fallback", ns["auto_radius"](cube) == ns["DEFAULT_RADIUS"])

# ---------------------------------------------------------------- create rig
reset()
target = make_target()
props = fresh_props(target)
props.radius = 0.0

op = ns["KR_OT_create_rig"]()
op.report = lambda t, m: print("    report:", t, m)
rv = op.execute(bpy.context)
check("create FINISHED", rv == {'FINISHED'})

pivot = db.get("Karuselka Pivot")
check("pivot created", pivot is not None and pivot.type == 'EMPTY')
check("pivot marked", pivot is not None and pivot.get("karuselka") == 1)
check("pivot at bbox center", pivot.location.xyz == (0.0, 0.0, 0.0),
      str(pivot.location))

cam = db.get("Karuselka Cam")
check("camera created", cam is not None and cam.type == 'CAMERA')
check("camera marked", cam.get("karuselka") == 1)
check("camera lens 50", cam.data.lens == 50.0)
check("camera dof off", cam.data.dof.use_dof is False)
check("camera parented to pivot", cam.parent is pivot)
check("camera at auto radius (3,0,0)",
      tuple(cam.location) == (3.0, 0.0, 0.0), str(tuple(cam.location)))

check("camera has 1 constraint", len(cam.constraints) == 1,
      str([c.type for c in cam.constraints]))
con = cam.constraints[0]
check("constraint TRACK_TO named", con.type == 'TRACK_TO' and con.name == "Karuselka Track")
check("constraint targets pivot", con.target is pivot)
check("constraint aim -Z up +Y",
      con.track_axis == 'TRACK_NEGATIVE_Z' and con.up_axis == 'UP_Y')

fc = z_fcurve(pivot)
check("z fcurve exists with 2 keys", fc is not None and len(fc.keyframe_points) == 2)
if fc and len(fc.keyframe_points) == 2:
    k1, k2 = fc.keyframe_points
    check("keys at frames 1 and 120", (k1.co[0], k2.co[0]) == (1.0, 120.0),
          str((k1.co, k2.co)))
    check("key values 0 and -tau (CW)", (k1.co[1], k2.co[1]) == (0.0, -TAU),
          str((k1.co[1], k2.co[1])))
    check("both keys LINEAR",
          k1.interpolation == 'LINEAR' and k2.interpolation == 'LINEAR',
          str((k1.interpolation, k2.interpolation)))
check("has_rig flag set", props.get("has_rig") == 1)
check("create leaves scene frame range alone", _scene.frame_end == 250)
check("create jumps to frame 1 (start of the rig)", _scene.frame_set_calls == [1],
      str(_scene.frame_set_calls))
check("parent_inverse reset to identity",
      cam.matrix_parent_inverse.t.xyz == (0.0, 0.0, 0.0),
      str(cam.matrix_parent_inverse.t))

# ---------------------------------------------------------------- no target
reset()
props = fresh_props()
op = ns["KR_OT_create_rig"]()
op.report = lambda t, m: print("    report:", t, m)
check("create without target -> CANCELLED", op.execute(bpy.context) == {'CANCELLED'})

# fallback to active object
target = make_target("ActiveCube")
bpy.context.active_object = target
rv = op.execute(bpy.context)
pivot = db.get("Karuselka Pivot")
check("create falls back to active object", rv == {'FINISHED'} and pivot is not None)
check("fallback pivot at active object center", pivot.location.xyz == (0.0, 0.0, 0.0))

# ---------------------------------------------------------------- user camera
reset()
target = make_target()
user_cam = db.new("User Cam", FakeCamData("User Cam"))
user_cam.data.lens = 85.0
user_cam.constraints.new('TRACK_TO').name = "Old Track"
user_cam.parent = db.new("Old Parent", None)          # UI-style old parenting
user_cam.matrix_parent_inverse = FakeMatrix((40.0, -25.0, 12.0))  # stale inverse
_scene.collection.objects.link(user_cam)
props = fresh_props(target)
props.camera = user_cam

op = ns["KR_OT_create_rig"]()
op.report = lambda t, m: print("    report:", t, m)
cameras_before = sum(1 for o in db if o.type == 'CAMERA')
rv = op.execute(bpy.context)
check("create with user camera FINISHED", rv == {'FINISHED'})
check("no extra camera created",
      sum(1 for o in db if o.type == 'CAMERA') == cameras_before)
check("user camera NOT marked", user_cam.get("karuselka") is None)
pivot = db.get("Karuselka Pivot")
check("user camera parented to pivot", user_cam.parent is pivot)
check("user camera stale parent_inverse reset",
      user_cam.matrix_parent_inverse.t.xyz == (0.0, 0.0, 0.0),
      str(user_cam.matrix_parent_inverse.t))
check("user camera placed at radius/height",
      tuple(user_cam.location) == (3.0, 0.0, 0.0), str(tuple(user_cam.location)))
check("user camera lens untouched", user_cam.data.lens == 85.0)
check("user camera got track constraint",
      any(c.name == "Karuselka Track" for c in user_cam.constraints))
check("old constraint kept",
      any(c.name == "Old Track" for c in user_cam.constraints))

# ---------------------------------------------------------------- repeat create
pivot_before = sum(1 for o in db if o.type == 'EMPTY')
rv = op.execute(bpy.context)
check("repeat create FINISHED", rv == {'FINISHED'})
check("repeat: still one pivot", sum(1 for o in db if o.type == 'EMPTY') == pivot_before)
check("repeat: still one camera",
      sum(1 for o in db if o.type == 'CAMERA') == cameras_before)
check("repeat: constraint not duplicated",
      sum(1 for c in user_cam.constraints if c.name == "Karuselka Track") == 1)

# ---------------------------------------------------------------- remove rig
# scene state: user camera rig from above + a foreign marked mesh + foreign cam
foreign = make_target("Foreign")
foreign["karuselka"] = 1     # someone else's marker — must survive
other_cam = db.new("Other Cam", FakeCamData("Other Cam"))
_scene.collection.objects.link(other_cam)

op_rm = ns["KR_OT_remove_rig"]()
op_rm.report = lambda t, m: print("    report:", t, m)
rv = op_rm.execute(bpy.context)
check("remove FINISHED", rv == {'FINISHED'})
check("pivot deleted", db.get("Karuselka Pivot") is None)
check("user camera survives", db.get("User Cam") is user_cam)
check("user camera unparented", user_cam.parent is None)
check("track constraint removed",
      not any(c.name == "Karuselka Track" for c in user_cam.constraints))
check("foreign constraint kept",
      any(c.name == "Old Track" for c in user_cam.constraints))
check("foreign marked mesh untouched", db.get("Foreign") is not None)
check("foreign camera untouched", db.get("Other Cam") is other_cam)
check("has_rig cleared", props.get("has_rig") == 0)
check("remove again -> CANCELLED", op_rm.execute(bpy.context) == {'CANCELLED'})

# remove own camera entirely
reset()
target = make_target()
props = fresh_props(target)
op = ns["KR_OT_create_rig"]()
op.report = lambda t, m: None
op.execute(bpy.context)
own_cam = db.get("Karuselka Cam")
rv = op_rm.execute(bpy.context)
check("remove own rig FINISHED", rv == {'FINISHED'})
check("own camera deleted", db.get("Karuselka Cam") is None)
check("own pivot deleted", db.get("Karuselka Pivot") is None)

# ---------------------------------------------------------------- render
reset()
props = fresh_props()
op_render = ns["KR_OT_render_turntable"]()
op_render.report = lambda t, m: print("    report:", t, m)
check("render without rig -> CANCELLED",
      op_render.execute(bpy.context) == {'CANCELLED'})

target = make_target()
props = fresh_props(target)
op = ns["KR_OT_create_rig"]()
op.report = lambda t, m: None
op.execute(bpy.context)
objects_before = len(db)
rv = op_render.execute(bpy.context)
check("render FINISHED", rv == {'FINISHED'})
check("frame range set 1..120",
      (_scene.frame_start, _scene.frame_end) == (1, 120),
      str((_scene.frame_start, _scene.frame_end)))
check("render filepath from output prop", _scene.render.filepath == "//turntable/",
      _scene.render.filepath)
check("render INVOKE animation=True",
      render_calls and render_calls[0][0] == ('INVOKE_DEFAULT',)
      and render_calls[0][1].get("animation") is True,
      str(render_calls))
check("render creates nothing", len(db) == objects_before)

props.output = "//turntable"   # no trailing slash
op_render.execute(bpy.context)
check("output slash normalized", _scene.render.filepath == "//turntable/",
      _scene.render.filepath)

# ---------------------------------------------------------------- slotted actions
# Blender 4.4+ slotted actions: no Action.fcurves, walk layers/strips/channelbags
legacy_action = types.SimpleNamespace(fcurves=FakeFCurves())
check("action fcurves: legacy branch",
      ns["_action_fcurves"](legacy_action) is legacy_action.fcurves)
bag = types.SimpleNamespace(fcurves=FakeFCurves())
slotted = types.SimpleNamespace(layers=[types.SimpleNamespace(strips=[
    types.SimpleNamespace(channelbags=[bag])])])
check("action fcurves: slotted branch", ns["_action_fcurves"](slotted) is bag.fcurves)
check("action fcurves: empty slotted -> None",
      ns["_action_fcurves"](types.SimpleNamespace(layers=[])) is None)

# ---------------------------------------------------------------- unregister
try:
    ns["unregister"]()
    check("unregister runs, classes removed", len(_registered) == 0,
          str(_registered))
except Exception:
    check("unregister runs, classes removed", False, traceback.format_exc())

# ---------------------------------------------------------------- summary
print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:")
    for name, detail in FAIL:
        print(" -", name, ("-- " + detail) if detail else "")
    sys.exit(1)
