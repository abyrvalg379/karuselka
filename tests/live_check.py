# Live headless check for KARUSELKA. Run inside Blender:
#   blender --background --factory-startup --python tests/live_check.py
# Validates icons against the real UI enum and the full rig lifecycle
# in a real Blender scene (render operator is NOT launched here).
import bpy
import importlib.util
import math
import os
import sys

FAILS = []


def check(name, cond, detail=""):
    print(("  OK " if cond else "FAIL ") + name + ((" -- " + str(detail)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


print("\n=== KARUSELKA live check, Blender", bpy.app.version_string, "===")

# ---------------------------------------------------------------- icons
param = bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon']
names = ({e.identifier for e in param.enum_items}
         or {e.identifier for e in param.enum_items_static})
for icon in ('ADD', 'X', 'RENDER_ANIMATION', 'CHECKMARK', 'CANCEL',
             'OBJECT_DATAMODE', 'CAMERA_DATA'):
    check(f"icon exists: {icon}", icon in names)

# ---------------------------------------------------------------- addon
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "extension", "__init__.py")
spec = importlib.util.spec_from_file_location("karuselka_live", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
check("module exec in Blender", True)
mod.register()
check("register ok", hasattr(bpy.types.Scene, "karuselka"))

scene = bpy.context.scene
target = context_target = bpy.context.active_object or scene.objects[0]
props = scene.karuselka
props.target = target
props.radius = 0.0

r = bpy.ops.karuselka.create_rig()
check("create FINISHED", r == {'FINISHED'}, r)
check("timeline follows rig (1..120)",
      (scene.frame_start, scene.frame_end) == (1, 120),
      (scene.frame_start, scene.frame_end))

pivot = bpy.data.objects.get("Karuselka Pivot")
cam = bpy.data.objects.get("Karuselka Cam")
check("pivot created EMPTY", pivot is not None and pivot.type == 'EMPTY')
check("camera created", cam is not None and cam.type == 'CAMERA')
check("both marked", pivot.get("karuselka") == 1 and cam.get("karuselka") == 1)
check("camera parented", cam.parent is pivot)
con = next((x for x in cam.constraints if x.type == 'TRACK_TO'), None)
check("track to pivot", con is not None and con.target is pivot
      and con.track_axis == 'TRACK_NEGATIVE_Z' and con.up_axis == 'UP_Y')
check("lens 50, dof off", cam.data.lens == 50.0 and not cam.data.dof.use_dof)
import mathutils
center = sum((target.matrix_world @ mathutils.Vector(c)
              for c in target.bound_box), mathutils.Vector()) / 8.0
check("pivot at bbox center", (pivot.location - center).length < 1e-5,
      f"{tuple(pivot.location)} vs {tuple(center)}")
check("camera at auto radius", cam.location.x > 0.0 and cam.location.y == 0.0
      and cam.location.z == 0.0, tuple(cam.location))
check("scene.camera is the rig camera", scene.camera is cam,
      scene.camera.name if scene.camera else None)
check("previous active camera remembered", props.get("prev_camera") == "Camera",
      props.get("prev_camera"))
check("clips are Blender defaults", abs(cam.data.clip_start - 0.1) < 1e-6
      and abs(cam.data.clip_end - 100.0) < 1e-6, (cam.data.clip_start, cam.data.clip_end))

fc = mod._action_fcurves(pivot.animation_data.action).find("rotation_euler", index=2)
check("z fcurve 2 keys", fc is not None and len(fc.keyframe_points) == 2)
if fc is not None and len(fc.keyframe_points) == 2:
    k1, k2 = fc.keyframe_points
    check("frames 1..120", (k1.co[0], k2.co[0]) == (1.0, 120.0),
          (k1.co[0], k2.co[0]))
    check("values 0..-tau", abs(k1.co[1]) < 1e-6 and abs(k2.co[1] + math.tau) < 1e-5,
          (k1.co[1], k2.co[1]))
    check("LINEAR", k1.interpolation == 'LINEAR' and k2.interpolation == 'LINEAR',
          (k1.interpolation, k2.interpolation))

# orbit actually moves the camera, and at constant speed (linear!)
# equal 30-frame windows: 1->31 and 31->61
scene.frame_set(1)
p1 = cam.matrix_world.translation.copy()
scene.frame_set(31)
p30 = cam.matrix_world.translation.copy()
scene.frame_set(61)
p60 = cam.matrix_world.translation.copy()
d1, d2 = (p30 - p1).length, (p60 - p30).length
check("camera orbits", (p60 - p1).length > 0.01, (p1 - p60).length)
check("constant speed (linear)", abs(d1 - d2) < 1e-3, (d1, d2))
view = (cam.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))).normalized()
to_pivot = (pivot.matrix_world.translation - cam.matrix_world.translation).normalized()
check("camera aims at the pivot", view.dot(to_pivot) > 0.999,
      round(view.dot(to_pivot), 5))

# frames edit in the panel retimes the rig and the timeline live
props.frames = 250
check("frames edit retimes timeline", scene.frame_end == 250, scene.frame_end)
fcl = mod._action_fcurves(pivot.animation_data.action).find(
    "rotation_euler", index=2)
lastk = fcl.keyframe_points[-1]
check("last keyframe slid to 250",
      abs(lastk.co[0] - 250.0) < 1e-5 and abs(lastk.co[1] + math.tau) < 1e-4
      and lastk.interpolation == 'LINEAR',
      [tuple(round(v, 3) for v in k.co) for k in fcl.keyframe_points])
scene.frame_set(125)
pmid = cam.matrix_world.translation.copy()
scene.frame_set(1)
check("orbit spans the new range", (pmid - cam.matrix_world.translation).length > 0.01)
props.frames = 120
check("timeline back to 120", scene.frame_end == 120, scene.frame_end)

# placement edits move the camera live
props.radius = 7.0
bpy.context.view_layer.update()
check("placement: radius moves camera live",
      abs(cam.matrix_world.translation.x - 7.0) < 1e-5
      and abs(cam.matrix_world.translation.z) < 1e-5,
      tuple(round(v, 3) for v in cam.matrix_world.translation))
props.height = 1.5
bpy.context.view_layer.update()
check("placement: height moves camera live",
      abs(cam.matrix_world.translation.z - 1.5) < 1e-5,
      round(cam.matrix_world.translation.z, 3))
props.radius = 0.0
props.height = 0.0

r = bpy.ops.karuselka.remove_rig()
check("remove FINISHED", r == {'FINISHED'}, r)
check("scene cleaned",
      bpy.data.objects.get("Karuselka Pivot") is None
      and bpy.data.objects.get("Karuselka Cam") is None)

# user camera survives removal
user_cam_data = bpy.data.cameras.new("My Cam")
user_cam = bpy.data.objects.new("My Cam", user_cam_data)
scene.collection.objects.link(user_cam)
props.camera = user_cam
bpy.ops.karuselka.create_rig()
check("user cam used", user_cam.parent is not None
      and any(x.name == "Karuselka Track" for x in user_cam.constraints))
bpy.ops.karuselka.remove_rig()
check("user cam survives remove", user_cam.name in bpy.data.objects
      and user_cam.parent is None
      and not any(x.name == "Karuselka Track" for x in user_cam.constraints))

# regression: create at frame != 1 used to leave the camera mid-orbit
# (e.g. at frame 60 it spawned behind the object and looked "random")
scene.frame_set(60)
props.camera = None
bpy.ops.karuselka.create_rig()
check("create jumps playhead to frame 1", scene.frame_current == 1,
      scene.frame_current)
cam2 = bpy.data.objects.get("Karuselka Cam")
check("camera starts at +X side of the object",
      cam2 is not None and cam2.matrix_world.translation.x > 2.9
      and abs(cam2.matrix_world.translation.y) < 1e-3,
      tuple(round(v, 3) for v in cam2.matrix_world.translation))
check("stale parent_inverse reset",
      cam2.matrix_parent_inverse == mathutils.Matrix()
      or tuple(cam2.matrix_parent_inverse.translation) == (0.0, 0.0, 0.0))
bpy.ops.karuselka.remove_rig()
check("scene cleaned again",
      bpy.data.objects.get("Karuselka Pivot") is None
      and bpy.data.objects.get("Karuselka Cam") is None)
check("scene.camera restored to the original",
      scene.camera is bpy.data.objects.get("Camera"),
      scene.camera.name if scene.camera else None)

# ---------------------------------------------------------------- object spin
scene.frame_set(1)
props.mode = 'OBJECT_SPIN'
props.camera = None
target.location = (4.0, -2.0, 1.0)   # off-origin: catches stale-matrix jumps
bpy.context.view_layer.update()
before = target.matrix_world.translation.copy()
r = bpy.ops.karuselka.create_rig()
check("spin create FINISHED", r == {'FINISHED'}, r)
spin = bpy.data.objects.get("KARUSELKA_Empty")
check("spin empty created", spin is not None and spin.get("karuselka") == 1)
check("target parented to spin", target.parent is spin)
check("target world position kept",
      (target.matrix_world.translation - before).length < 1e-5)
cam_s = bpy.data.objects.get("Karuselka Cam")
check("spin camera static (unparented)", cam_s.parent is None)
scene.frame_set(1)
t1, c1 = target.matrix_world.copy(), cam_s.matrix_world.translation.copy()
scene.frame_set(31)
t31, c31 = target.matrix_world.copy(), cam_s.matrix_world.translation.copy()
scene.frame_set(61)
t61, c61 = target.matrix_world.copy(), cam_s.matrix_world.translation.copy()
a1 = t1.to_quaternion().rotation_difference(t31.to_quaternion()).angle
a2 = t31.to_quaternion().rotation_difference(t61.to_quaternion()).angle
# quaternion double-cover: normalize to the shortest arc
a1, a2 = min(a1, 2 * math.pi - a1), min(a2, 2 * math.pi - a2)
check("object rotates at constant speed", a1 > 0.1 and abs(a1 - a2) < 1e-3,
      (a1, a2))
check("camera does not move in spin mode",
      (c31 - c1).length < 1e-5 and (c61 - c31).length < 1e-5)
r = bpy.ops.karuselka.remove_rig()
check("spin remove FINISHED", r == {'FINISHED'}, r)
check("spin rig fully removed",
      bpy.data.objects.get("KARUSELKA_Empty") is None
      and target.parent is None)
props.mode = 'CAMERA_ORBIT'

# spin with existing parent: the hierarchy root is parented, not the target
anchor = bpy.data.objects.new("KarAnchor", None)
scene.collection.objects.link(anchor)
target.parent = anchor
target.matrix_parent_inverse = anchor.matrix_world.inverted()
props.mode = 'OBJECT_SPIN'
bpy.ops.karuselka.create_rig()
spin = bpy.data.objects.get("KARUSELKA_Empty")
check("spin+parent: empty created", spin is not None)
check("spin+parent: hierarchy root parented to empty", anchor.parent is spin)
check("spin+parent: target keeps its own parent", target.parent is anchor)
before_t = target.matrix_world.translation.copy()
q_a = target.matrix_world.to_quaternion()
scene.frame_set(60)
q_b = target.matrix_world.to_quaternion()
check("spin+parent: target rotates via its root",
      (target.matrix_world.translation - before_t).length < 1e-5
      and q_a.rotation_difference(q_b).angle > 0.1)
bpy.ops.karuselka.remove_rig()
check("spin+parent: root freed on remove", anchor.parent is None)
check("spin+parent: target still under its parent", target.parent is anchor)
bpy.data.objects.remove(anchor, do_unlink=True)
props.mode = 'CAMERA_ORBIT'

# ---------------------------------------------------------------- keep settings
props.keep_settings = True
bpy.ops.karuselka.create_rig()
bpy.data.objects["Karuselka Cam"].data.lens = 85.0
bpy.data.objects["Karuselka Cam"].data.clip_start = 0.2
bpy.ops.karuselka.create_rig()
check("keep: lens survives rebuild",
      bpy.data.objects["Karuselka Cam"].data.lens == 85.0)
check("keep: clips survive rebuild",
      abs(bpy.data.objects["Karuselka Cam"].data.clip_start - 0.2) < 1e-6)
props.keep_settings = False
bpy.ops.karuselka.create_rig()
check("no-keep: lens back to default",
      bpy.data.objects["Karuselka Cam"].data.lens == 50.0)

# panel edits push into the rig camera (update callback)
props.lens = 65.0
check("panel lens edit -> live camera",
      bpy.data.objects["Karuselka Cam"].data.lens == 65.0)
bpy.ops.karuselka.remove_rig()

# ---------------------------------------------------------------- assembly
coll = bpy.data.collections.new("KarAssembly")
scene.collection.children.link(coll)
mesh = bpy.data.meshes.new("AsmMesh")
part = bpy.data.objects.new("AsmPart", mesh)
part.location = (9.0, 0.0, 0.0)
coll.objects.link(part)
coll.objects.link(target)
props.collection = coll
props.mode = 'OBJECT_SPIN'
props.camera = None
r = bpy.ops.karuselka.create_rig()
spin = bpy.data.objects.get("KARUSELKA_Empty")
check("assembly: spin created", r == {'FINISHED'} and spin is not None)
lo = [1e9] * 3
hi = [-1e9] * 3
for ob in (target, part):
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        lo = [min(a, b) for a, b in zip(lo, w)]
        hi = [max(a, b) for a, b in zip(hi, w)]
cx = (lo[0] + hi[0]) / 2.0
check("assembly: spin at combined center",
      spin is not None and abs(spin.location.x - cx) < 1e-5,
      (round(spin.location.x, 4), round(cx, 4)))
check("assembly: roots parented",
      target.parent is spin and part.parent is spin)
bpy.ops.karuselka.remove_rig()
check("assembly: roots freed", target.parent is None and part.parent is None)
bpy.data.collections.remove(coll)
props.collection = None
props.mode = 'CAMERA_ORBIT'

# ---------------------------------------------------------------- 3D cursor center
scene.cursor.location = (6.0, 1.0, 1.0)
props.center = 'CURSOR'
props.camera = None
r = bpy.ops.karuselka.create_rig()
pivot_c = bpy.data.objects.get("Karuselka Pivot")
check("cursor center: pivot at cursor",
      r == {'FINISHED'} and pivot_c is not None
      and (pivot_c.location - mathutils.Vector((6.0, 1.0, 1.0))).length < 1e-5,
      tuple(round(v, 3) for v in pivot_c.location) if pivot_c else None)
cur_cam = props.camera
check("cursor center: camera follows the pivot",
      cur_cam is not None and cur_cam.parent is pivot_c)
bpy.ops.karuselka.remove_rig()
props.center = 'BOUNDS'

mod.unregister()
check("unregister ok", not hasattr(bpy.types.Scene, "karuselka"))

print(f"\n=== {len(FAILS)} failed ===")
for f in FAILS:
    print(" -", f)
