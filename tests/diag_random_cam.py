# Diagnostic: which scenarios put the camera somewhere unexpected?
# blender --background --factory-startup --python tests/diag_random_cam.py
import bpy
import importlib.util
import math
import os

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "extension", "__init__.py")
spec = importlib.util.spec_from_file_location("karuselka_diag", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()

scene = bpy.context.scene
props = scene.karuselka


def pos(ob):
    return tuple(round(v, 3) for v in ob.matrix_world.translation)


def fresh_rig():
    bpy.ops.karuselka.remove_rig()
    scene.frame_set(1)
    props.camera = None
    props.target = bpy.data.objects["Cube"]
    props.radius = 0.0


# A: baseline, frame 1
fresh_rig()
bpy.ops.karuselka.create_rig()
pivot = bpy.data.objects["Karuselka Pivot"]
cam = bpy.data.objects["Karuselka Cam"]
print("A baseline:   pivot", pos(pivot), "cam", pos(cam),
      "cam_local", tuple(round(v, 3) for v in cam.location),
      "parent_inv_is_identity", cam.matrix_parent_inverse == __import__("mathutils").Matrix())

# B: create at frame 60 (not 1)
fresh_rig()
scene.frame_set(60)
bpy.ops.karuselka.create_rig()
cam = bpy.data.objects["Karuselka Cam"]
print("B create@f60: cam world", pos(cam), "(on orbit but at 180 deg)")
bpy.ops.karuselka.remove_rig()
scene.frame_set(1)

# C: user camera previously parented via UI (non-identity matrix_parent_inverse)
fresh_rig()
uc = bpy.data.objects.new("User Cam", bpy.data.cameras.new("User Cam"))
scene.collection.objects.link(uc)
anchor = bpy.data.objects.new("Anchor", None)
scene.collection.objects.link(anchor)
anchor.location = (40.0, -25.0, 12.0)
uc.parent = anchor
uc.matrix_parent_inverse = anchor.matrix_world.inverted()   # what Ctrl+P does
uc.location = (2.0, 3.0, 4.0)
props.camera = uc
bpy.ops.karuselka.create_rig()
print("C ui-parented user cam: world", pos(uc),
      "expected on orbit ~(3,0,0)" if uc.matrix_parent_inverse ==
      __import__("mathutils").Matrix() else "  <-- RANDOM PLACE (parent_inverse survived)")
bpy.ops.karuselka.remove_rig()

# D: target with rotation+scale+location
fresh_rig()
cube = bpy.data.objects["Cube"]
cube.location = (10.0, 5.0, 3.0)
cube.rotation_euler = (0.4, 0.0, 0.8)
cube.scale = (1.0, 2.0, 1.0)
bpy.context.view_layer.update()
bpy.ops.karuselka.create_rig()
pivot = bpy.data.objects["Karuselka Pivot"]
cam = bpy.data.objects["Karuselka Cam"]
corners = [cube.matrix_world @ __import__("mathutils").Vector(c) for c in cube.bound_box]
expect = sum(corners, __import__("mathutils").Vector()) / 8.0
d = (pivot.matrix_world.translation - expect).length
print("D transformed target: pivot", pos(pivot), "bbox center", tuple(round(v, 3) for v in expect),
      "delta", round(d, 6), "cam-pivot dist", round((cam.matrix_world.translation - pivot.matrix_world.translation).length, 3))

mod.unregister()
print("diag done")
