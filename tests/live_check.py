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
check("clips sized to orbit (1000:1)",
      abs(cam.data.clip_start - 0.03) < 1e-6
      and abs(cam.data.clip_end - 30.0) < 1e-6, (cam.data.clip_start, cam.data.clip_end))

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

mod.unregister()
check("unregister ok", not hasattr(bpy.types.Scene, "karuselka"))

print(f"\n=== {len(FAILS)} failed ===")
for f in FAILS:
    print(" -", f)
