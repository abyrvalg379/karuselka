bl_info = {
    "name": "KARUSELKA",
    "author": "Maksim Kovalev",
    "version": (1, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > KARUSELKA",
    "description": "Turntable rig: camera orbit or object spin, linear keyframes + animation render",
    "doc_url": "https://github.com/abyrvalg379/karuselka",
    "license": "GPL-3.0-or-later",
    "category": "Animation",
}

"""KARUSELKA — fast camera turntable rig for model showreels."""

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Maksim Kovalev

import math

import bpy
from mathutils import Matrix, Vector
from bpy.props import (
    IntProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    StringProperty,
    PointerProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

PIVOT_NAME = "Karuselka Pivot"
SPIN_NAME = "KARUSELKA_Empty"
CAM_NAME = "Karuselka Cam"
TRACK_NAME = "Karuselka Track"
MARKER = "karuselka"          # custom prop = 1 on everything the rig owns
DEFAULT_RADIUS = 2.0          # fallback when the target has no dimensions


# ---------------------------------------------------------------------------
#  Pure helpers — unit-tested by tests/test_mock.py without Blender
# ---------------------------------------------------------------------------

def turn_end_frame(frames, rounds):
    """Total rig length in frames; at least 2 so interpolation exists."""
    return max(2, int(round(frames * rounds)))


def turn_end_angle(rounds, direction):
    """Signed total rotation in radians (CW orbit = negative Z rotation)."""
    sign = -1.0 if direction == 'CW' else 1.0
    return sign * math.tau * rounds


def auto_radius(dims, margin):
    """Orbit radius: largest extent x margin."""
    radius = max(dims) * margin if dims else 0.0
    if radius <= 0.0:
        radius = DEFAULT_RADIUS
    return radius


def combined_bounds(obs):
    """(center, dims) of the world-space bounding box over all objects."""
    lo = [float("inf")] * 3
    hi = [-float("inf")] * 3
    for ob in obs:
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    center = Vector(((lo[0] + hi[0]) / 2.0,
                     (lo[1] + hi[1]) / 2.0,
                     (lo[2] + hi[2]) / 2.0))
    dims = Vector((hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))
    return center, dims


def _collection_objects(coll, out, seen):
    if coll.name in seen:
        return
    seen.add(coll.name)
    for ob in coll.objects:
        out.append(ob)
    for child in coll.children:
        _collection_objects(child, out, seen)


def _scope_objects(props):
    """Objects the turntable acts on: everything in the collection scope
    (rig objects excluded) or the single target."""
    if props.collection is not None:
        found = []
        _collection_objects(props.collection, found, set())
        uniq = {}
        for ob in found:
            if ob.get(MARKER, 0) != 1:
                uniq[ob.name] = ob
        return list(uniq.values())
    return [props.target] if props.target is not None else []


def find_marked_empties(scene):
    """Rig helper empties (orbit pivot and/or spin), or an empty list."""
    return [ob for ob in scene.objects
            if ob.type == 'EMPTY' and ob.get(MARKER, 0) == 1]


def find_own_cameras(scene):
    """Cameras marked as rig-owned. The user's camera is never marked."""
    return [ob for ob in scene.objects
            if ob.type == 'CAMERA' and ob.get(MARKER, 0) == 1]


def _action_fcurves(action):
    """Fcurves collection across legacy and slotted (4.4+) actions —
    Action.fcurves does not exist on 5.x slotted actions."""
    if hasattr(action, "fcurves"):
        return action.fcurves
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                return bag.fcurves
    return None


def _force_linear(rot_obj):
    """Bezier easing ruins constant rotation speed — force LINEAR."""
    ad = rot_obj.animation_data
    action = ad.action if ad else None
    if action is None:
        return
    fcurves = _action_fcurves(action)
    fc = fcurves.find("rotation_euler", index=2) if fcurves else None
    if fc is not None:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


def _clear_parent_keep_transform(ob):
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw


def _apply_camera_settings(self, context):
    """Panel edits go straight into the rig camera, live."""
    scene = context.scene if context else None
    props = getattr(scene, "karuselka", None) if scene else None
    cam = props.camera if props else None
    if cam is not None and cam.type == 'CAMERA':
        cam.data.lens = self.lens
        cam.data.dof.use_dof = self.use_dof
        cam.data.clip_start = self.clip_start
        cam.data.clip_end = self.clip_end


def _remove_rig_objects(context):
    """Delete everything marked karuselka; a user camera only loses
    the track constraint and the parenting. Returns True if a rig existed."""
    scene = context.scene
    props = scene.karuselka
    empties = find_marked_empties(scene)

    user_cam = props.camera
    if user_cam is not None and user_cam.get(MARKER, 0) == 1:
        user_cam = None    # ours — deleted below with the rest

    # scene.camera back to what it was, but only if it still is the rig's
    cur = scene.camera
    used = props.camera
    if cur is not None and (cur == used or cur.get(MARKER, 0) == 1):
        prev_name = props.get("prev_camera", "")
        scene.camera = bpy.data.objects.get(prev_name) if prev_name else None

    # spin mode parents the target (and orbit mode the camera) — undo that
    for e in empties:
        for child in list(e.children):
            _clear_parent_keep_transform(child)

    if user_cam is not None and empties:
        for con in list(user_cam.constraints):
            if (con.type == 'TRACK_TO' and con.name == TRACK_NAME
                    and any(con.target == e for e in empties)):
                user_cam.constraints.remove(con)

    removed = bool(empties)
    for cam in find_own_cameras(scene):
        bpy.data.objects.remove(cam, do_unlink=True)
        removed = True
    for e in empties:
        bpy.data.objects.remove(e, do_unlink=True)
    if props.camera is not None and props.camera.name not in scene.objects:
        props.camera = None    # stale pointer insurance
    props["has_rig"] = 0
    return removed


# ---------------------------------------------------------------------------
#  Properties
# ---------------------------------------------------------------------------

def _update_rig_timing(self, context):
    """Frames/Rounds/Direction edits retime the existing rig live: the last
    keyframe slides to the new end and the timeline follows."""
    scene = context.scene if context else None
    props = getattr(scene, "karuselka", None) if scene else None
    if props is None or scene is None:
        return
    rot_obj = None
    for e in find_marked_empties(scene):
        ad = e.animation_data
        if ad is not None and ad.action is not None:
            rot_obj = e
            break
    if rot_obj is None:
        return
    fcurves = _action_fcurves(rot_obj.animation_data.action)
    fc = fcurves.find("rotation_euler", index=2) if fcurves else None
    if fc is None or not fc.keyframe_points:
        return
    end_f = turn_end_frame(props.frames, props.rounds)
    fc.keyframe_points[-1].co = (float(end_f),
                                 turn_end_angle(props.rounds, props.direction))
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.update()
    scene.frame_start = 1
    scene.frame_end = end_f


def _update_rig_placement(self, context):
    """Radius/Margin/Height edits move the rig camera live; with Auto Clip
    the near/far planes follow the new distance at a fixed 1000:1 ratio."""
    scene = context.scene if context else None
    props = getattr(scene, "karuselka", None) if scene else None
    cam = props.camera if props else None
    if props is None or scene is None or cam is None or cam.type != 'CAMERA':
        return
    empties = find_marked_empties(scene)
    if not empties:
        return
    scope = _scope_objects(props)
    if props.radius > 0.0:
        radius = props.radius
    elif scope:
        radius = auto_radius(combined_bounds(scope)[1], props.margin)
    else:
        # target cleared/deleted — fall back to the radius used at create
        radius = props.get("last_radius", 0.0) or DEFAULT_RADIUS
    center = empties[0].location    # pivot/spin sits at the rotation center
    if cam.parent is not None:      # orbit: location is pivot-local
        cam.location = (radius, 0.0, props.height)
    else:                           # spin: camera is unparented = world space
        cam.location = center + Vector((radius, 0.0, props.height))


def _poll_camera(_self, obj):
    return obj.type == 'CAMERA'


class KR_SceneSettings(PropertyGroup):
    mode: EnumProperty(
        name="Mode",
        description="Camera orbits the object, or the object spins on its axis",
        items=(
            ('CAMERA_ORBIT', "Camera", "Camera orbits around the object"),
            ('OBJECT_SPIN', "Object", "Object rotates on its axis, camera is static"),
        ),
        default='CAMERA_ORBIT',
    )
    target: PointerProperty(
        name="Target",
        description="Object to turntable (falls back to the active object)",
        type=bpy.types.Object,
    )
    collection: PointerProperty(
        name="Collection",
        description="Turntable everything in this collection "
                    "(overrides the Target)",
        type=bpy.types.Collection,
    )
    camera: PointerProperty(
        name="Camera",
        description="Camera to use; leave empty to auto-create one",
        type=bpy.types.Object,
        poll=_poll_camera,
    )
    frames: IntProperty(
        name="Frames",
        description="Frames per full revolution (fps is taken from the scene)",
        default=120,
        min=2,
        update=_update_rig_timing,
    )
    rounds: FloatProperty(
        name="Rounds",
        description="Number of revolutions, fractional is allowed",
        default=1.0,
        min=0.1,
        soft_max=10.0,
        update=_update_rig_timing,
    )
    radius: FloatProperty(
        name="Radius",
        description="Orbit distance, 0 = auto (object size x Margin)",
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
        update=_update_rig_placement,
    )
    margin: FloatProperty(
        name="Margin",
        description="Auto radius multiplier on the object size (bigger = farther)",
        default=2.5,
        min=1.1,
        soft_max=10.0,
        update=_update_rig_placement,
    )
    height: FloatProperty(
        name="Height",
        description="Camera height relative to the object center",
        default=0.0,
        subtype='DISTANCE',
        update=_update_rig_placement,
    )
    direction: EnumProperty(
        name="Dir",
        description="Rotation direction (viewed from above)",
        items=(
            ('CW', "CW", "Clockwise when viewed from above"),
            ('CCW', "CCW", "Counter-clockwise when viewed from above"),
        ),
        default='CW',
        update=_update_rig_timing,
    )
    lens: FloatProperty(
        name="Lens",
        description="Focal length for the rig camera",
        default=50.0,
        min=1.0,
        soft_max=300.0,
        update=_apply_camera_settings,
    )
    use_dof: BoolProperty(
        name="DoF",
        description="Depth of field on the rig camera",
        default=False,
        update=_apply_camera_settings,
    )
    clip_start: FloatProperty(
        name="Clip Start",
        description="Near clipping of the rig camera",
        default=0.1,
        min=0.0001,
        soft_min=0.001,
        unit='LENGTH',
        update=_apply_camera_settings,
    )
    clip_end: FloatProperty(
        name="Clip End",
        description="Far clipping of the rig camera",
        default=100.0,
        min=0.01,
        unit='LENGTH',
        update=_apply_camera_settings,
    )
    keep_settings: BoolProperty(
        name="Keep Settings",
        description="Rebuild reuses the previous camera's lens/DoF/clips "
                    "instead of defaults",
        default=False,
    )
    output: StringProperty(
        name="Output",
        description="Render output path for the turntable frames",
        default="//turntable/",
        subtype='DIR_PATH',
    )


# ---------------------------------------------------------------------------
#  Operators
# ---------------------------------------------------------------------------

class KR_OT_create_rig(Operator):
    bl_idname = "karuselka.create_rig"
    bl_label = "Create Rig"
    bl_description = "Create the turntable rig with keyframes (rebuilds an existing rig)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.karuselka
        target = props.target
        if target is None:
            target = context.active_object
        if target is None and props.collection is None:
            self.report({'ERROR'},
                        "No scope: set a Target, a Collection or select an object")
            return {'CANCELLED'}
        scope = _scope_objects(props)
        if not scope:
            if props.collection is not None:
                self.report({'ERROR'}, "The Collection is empty")
                return {'CANCELLED'}
            scope = [target]    # active-object fallback
        scope_name = (props.collection.name if props.collection
                      else target.name)

        # keep-settings: capture the previous camera BEFORE it is deleted
        prev = None
        if props.keep_settings:
            prev_cam = props.camera
            if prev_cam is None or prev_cam.get(MARKER, 0) != 1:
                cams = find_own_cameras(context.scene)
                prev_cam = cams[0] if cams else None
            if prev_cam is not None and prev_cam.type == 'CAMERA':
                prev = {"lens": prev_cam.data.lens,
                        "dof": prev_cam.data.dof.use_dof,
                        "cs": prev_cam.data.clip_start,
                        "ce": prev_cam.data.clip_end}

        # one rig at a time: drop the previous one (markers only)
        _remove_rig_objects(context)

        radius = (props.radius if props.radius > 0.0
                  else auto_radius(combined_bounds(scope)[1], props.margin))
        props["last_radius"] = radius    # placement fallback if scope goes away
        center, _ = combined_bounds(scope)

        if prev is not None:
            lens, dof = prev["lens"], prev["dof"]
            cs, ce = prev["cs"], prev["ce"]
        else:
            # fresh defaults every time — insurance against inherited junk
            lens, dof = 50.0, False
            cs, ce = 0.1, 100.0          # Blender factory defaults
        props.lens, props.use_dof = lens, dof
        props.clip_start, props.clip_end = cs, ce

        end_f = turn_end_frame(props.frames, props.rounds)
        angle = turn_end_angle(props.rounds, props.direction)

        if props.mode == 'OBJECT_SPIN':
            # rotate the hierarchy roots of the whole scope: an object with
            # an existing parent contributes its parent chain root instead
            rot_obj = bpy.data.objects.new(SPIN_NAME, None)
            rot_obj.empty_display_type = 'PLAIN_AXES'
            context.scene.collection.objects.link(rot_obj)
            rot_obj[MARKER] = 1
            rot_obj.location = center

            roots = {}
            for ob in scope:
                r = ob
                while r.parent is not None:
                    r = r.parent
                roots[r.name] = r
            for r in roots.values():
                r.parent = rot_obj
                # exact inverse without depending on depsgraph-evaluated
                # matrix_world of the freshly created empty (it is stale here)
                r.matrix_parent_inverse = Matrix.Translation(-center)

            cam = props.camera
            if cam is None:
                cam = self._new_camera(context)
                props.camera = cam
            if cam.parent is not None:
                _clear_parent_keep_transform(cam)
            # camera is unparented here, so location is world space
            cam.location = center + Vector((radius, 0.0, props.height))
        else:
            # camera orbits: keyframes on the pivot, camera parented to it
            rot_obj = bpy.data.objects.new(PIVOT_NAME, None)
            rot_obj.empty_display_type = 'PLAIN_AXES'
            context.scene.collection.objects.link(rot_obj)
            rot_obj[MARKER] = 1
            rot_obj.location = center

            cam = props.camera
            if cam is None:
                cam = self._new_camera(context)
                props.camera = cam
            # orbit from parenting, aiming from the constraint — no doubled
            # rotation; a stale matrix_parent_inverse drags the camera away
            cam.parent = rot_obj
            cam.matrix_parent_inverse = Matrix()
            cam.location = (radius, 0.0, props.height)

        for con in list(cam.constraints):
            if con.name == TRACK_NAME:
                cam.constraints.remove(con)
        con = cam.constraints.new('TRACK_TO')
        con.name = TRACK_NAME
        con.target = rot_obj
        con.track_axis = 'TRACK_NEGATIVE_Z'
        con.up_axis = 'UP_Y'

        cam.data.lens = lens
        cam.data.dof.use_dof = dof
        cam.data.clip_start = cs
        cam.data.clip_end = ce

        rot_obj.rotation_euler = (0.0, 0.0, 0.0)
        rot_obj.keyframe_insert(data_path="rotation_euler", frame=1)
        rot_obj.rotation_euler = (0.0, 0.0, angle)
        rot_obj.keyframe_insert(data_path="rotation_euler", frame=end_f)
        _force_linear(rot_obj)

        # Numpad 0 and the render look through scene.camera — point it at
        # the rig camera; Remove Rig puts the previous one back
        cur = context.scene.camera
        if cur is None or cur.get(MARKER, 0) != 1:
            props["prev_camera"] = cur.name if cur else ""
        context.scene.camera = cam

        props["has_rig"] = 1
        # timeline follows the rig: no manual frame-range fiddling
        context.scene.frame_start = 1
        context.scene.frame_end = end_f
        # show the rig from its start: at any other frame the camera sits
        # at that frame's orbit angle and looks like it spawned "randomly"
        context.scene.frame_set(1)
        mode = "object spin" if props.mode == 'OBJECT_SPIN' else "camera orbit"
        self.report({'INFO'}, f"Turntable rig ready: {scope_name}, "
                              f"{mode}, frames 1..{end_f}")
        return {'FINISHED'}

    @staticmethod
    def _new_camera(context):
        cam_data = bpy.data.cameras.new(CAM_NAME)
        cam_data.lens = 50.0
        cam_data.dof.use_dof = False
        cam = bpy.data.objects.new(CAM_NAME, cam_data)
        context.scene.collection.objects.link(cam)
        cam[MARKER] = 1
        return cam


class KR_OT_remove_rig(Operator):
    bl_idname = "karuselka.remove_rig"
    bl_label = "Remove Rig"
    bl_description = "Remove the rig (keeps the user camera, removes only what KARUSELKA created)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _remove_rig_objects(context):
            self.report({'INFO'}, "Turntable rig removed")
            return {'FINISHED'}
        self.report({'WARNING'}, "No KARUSELKA rig in the scene")
        return {'CANCELLED'}


class KR_OT_render_turntable(Operator):
    bl_idname = "karuselka.render_turntable"
    bl_label = "Render Turntable"
    bl_description = "Render the animation to the output path (uses current engine settings)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        props = scene.karuselka
        if not find_marked_empties(scene):
            self.report({'ERROR'}, "Create the rig first")
            return {'CANCELLED'}

        end_f = turn_end_frame(props.frames, props.rounds)
        scene.frame_start = 1
        scene.frame_end = end_f
        out = props.output or "//turntable/"
        if not out.endswith(("/", "\\")):
            out += "/"
        scene.render.filepath = out

        if not any(o.type == 'LIGHT' for o in scene.objects):
            self.report({'WARNING'}, "No lights in the scene — "
                                     "the render may come out dark")

        # non-blocking: the render window takes over from here
        bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
        self.report({'INFO'}, f"Rendering frames 1..{end_f}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Panel
# ---------------------------------------------------------------------------

class KR_PT_main_panel(Panel):
    bl_label = "KARUSELKA"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "KARUSELKA"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.karuselka

        active = bool(find_marked_empties(scene))
        row = layout.row()
        row.label(text="Rig active" if active else "No rig",
                  icon='CHECKMARK' if active else 'CANCEL')

        layout.row().prop(props, "mode", expand=True)

        col = layout.column(align=True)
        col.prop(props, "target")
        col.prop(props, "collection")
        col.prop(props, "camera")
        col.separator()
        col.prop(props, "frames")
        col.prop(props, "rounds")
        col.prop(props, "radius")
        col.prop(props, "margin")
        col.prop(props, "height")
        col.prop(props, "direction")
        col.separator()
        col.label(text="Camera:")
        col.prop(props, "lens")
        col.prop(props, "use_dof")
        row = col.row(align=True)
        row.prop(props, "clip_start")
        row.prop(props, "clip_end")
        col.prop(props, "keep_settings")
        col.separator()
        col.prop(props, "output")

        end_f = turn_end_frame(props.frames, props.rounds)
        fps = scene.render.fps or 24
        layout.label(text=f"~{end_f / fps:.1f} s, {end_f} frames")

        row = layout.row(align=True)
        row.operator("karuselka.create_rig", icon='ADD')
        row.operator("karuselka.remove_rig", icon='X')
        layout.operator("karuselka.render_turntable", icon='RENDER_ANIMATION')


# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------

classes = (
    KR_SceneSettings,
    KR_OT_create_rig,
    KR_OT_remove_rig,
    KR_OT_render_turntable,
    KR_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.karuselka = PointerProperty(type=KR_SceneSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    try:
        del bpy.types.Scene.karuselka
    except Exception:
        pass


if __name__ == "__main__":
    register()
