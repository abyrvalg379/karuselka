"""KARUSELKA — fast camera turntable rig for model showreels."""

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Maksim Kovalev

import math

import bpy
from mathutils import Matrix, Vector
from bpy.props import (
    IntProperty,
    FloatProperty,
    EnumProperty,
    StringProperty,
    PointerProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

PIVOT_NAME = "Karuselka Pivot"
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


def bbox_center_world(ob):
    """World-space center of the object's bounding box."""
    corners = ob.bound_box
    center = Vector((0.0, 0.0, 0.0))
    for c in corners:
        center += ob.matrix_world @ Vector(c)
    return center / float(len(corners))


def auto_radius(ob):
    """Orbit radius from the object's largest dimension (50 mm lens margin)."""
    radius = max(ob.dimensions) * 1.5 if ob.dimensions else 0.0
    if radius <= 0.0:
        radius = DEFAULT_RADIUS
    return radius


def find_pivot(scene):
    """The rig's pivot empty, or None."""
    for ob in scene.objects:
        if ob.type == 'EMPTY' and ob.get(MARKER, 0) == 1:
            return ob
    return None


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


def _force_linear(pivot):
    """Bezier easing ruins constant orbit speed — force LINEAR everywhere."""
    ad = pivot.animation_data
    action = ad.action if ad else None
    if action is None:
        return
    fcurves = _action_fcurves(action)
    fc = fcurves.find("rotation_euler", index=2) if fcurves else None
    if fc is not None:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'


def _remove_rig_objects(context):
    """Delete everything marked karuselka; a user camera only loses
    the track constraint and the parenting. Returns True if a rig existed."""
    scene = context.scene
    props = scene.karuselka
    pivot = find_pivot(scene)

    user_cam = props.camera
    if user_cam is not None and user_cam.get(MARKER, 0) == 1:
        user_cam = None    # ours — deleted below with the rest

    if user_cam is not None and pivot is not None:
        for con in list(user_cam.constraints):
            if (con.type == 'TRACK_TO' and con.name == TRACK_NAME
                    and con.target == pivot):
                user_cam.constraints.remove(con)
        mw = user_cam.matrix_world.copy()
        user_cam.parent = None
        user_cam.matrix_world = mw

    removed = False
    for cam in find_own_cameras(scene):
        bpy.data.objects.remove(cam, do_unlink=True)
        removed = True
    if pivot is not None:
        bpy.data.objects.remove(pivot, do_unlink=True)
        removed = True
    props["has_rig"] = 0
    return removed


# ---------------------------------------------------------------------------
#  Properties
# ---------------------------------------------------------------------------

def _poll_camera(_self, obj):
    return obj.type == 'CAMERA'


class KR_SceneSettings(PropertyGroup):
    target: PointerProperty(
        name="Target",
        description="Object to orbit around (falls back to the active object)",
        type=bpy.types.Object,
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
    )
    rounds: FloatProperty(
        name="Rounds",
        description="Number of revolutions, fractional is allowed",
        default=1.0,
        min=0.1,
        soft_max=10.0,
    )
    radius: FloatProperty(
        name="Radius",
        description="Orbit radius, 0 = auto (object size x 1.5)",
        default=0.0,
        min=0.0,
        subtype='DISTANCE',
    )
    height: FloatProperty(
        name="Height",
        description="Camera height relative to the object center",
        default=0.0,
        subtype='DISTANCE',
    )
    direction: EnumProperty(
        name="Dir",
        description="Orbit direction (viewed from above)",
        items=(
            ('CW', "CW", "Clockwise when viewed from above"),
            ('CCW', "CCW", "Counter-clockwise when viewed from above"),
        ),
        default='CW',
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
    bl_description = "Create the orbit rig with keyframes (rebuilds an existing rig)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.karuselka
        target = props.target
        if target is None:
            target = context.active_object
        if target is None:
            self.report({'ERROR'}, "No target: assign one or select an object")
            return {'CANCELLED'}

        # one rig at a time: drop the previous one (markers only)
        _remove_rig_objects(context)

        pivot = bpy.data.objects.new(PIVOT_NAME, None)
        pivot.empty_display_type = 'PLAIN_AXES'
        context.scene.collection.objects.link(pivot)
        pivot[MARKER] = 1
        pivot.location = bbox_center_world(target)

        cam = props.camera
        if cam is None:
            cam_data = bpy.data.cameras.new(CAM_NAME)
            cam_data.lens = 50.0
            cam_data.dof.use_dof = False
            cam = bpy.data.objects.new(CAM_NAME, cam_data)
            context.scene.collection.objects.link(cam)
            cam[MARKER] = 1
            props.camera = cam

        # orbit from parenting, aiming from the constraint — no doubled rotation
        cam.parent = pivot
        # a camera parented earlier (UI or another rig) keeps a stale
        # matrix_parent_inverse — that drags it to a random spot on 3.6–4.x
        cam.matrix_parent_inverse = Matrix()
        radius = props.radius if props.radius > 0.0 else auto_radius(target)
        cam.location = (radius, 0.0, props.height)

        for con in list(cam.constraints):
            if con.name == TRACK_NAME:
                cam.constraints.remove(con)
        con = cam.constraints.new('TRACK_TO')
        con.name = TRACK_NAME
        con.target = pivot
        con.track_axis = 'TRACK_NEGATIVE_Z'
        con.up_axis = 'UP_Y'

        end_f = turn_end_frame(props.frames, props.rounds)
        pivot.rotation_euler = (0.0, 0.0, 0.0)
        pivot.keyframe_insert(data_path="rotation_euler", frame=1)
        pivot.rotation_euler = (0.0, 0.0,
                                turn_end_angle(props.rounds, props.direction))
        pivot.keyframe_insert(data_path="rotation_euler", frame=end_f)
        _force_linear(pivot)

        props["has_rig"] = 1
        # show the rig from its start: at any other frame the camera sits
        # at that frame's orbit angle and looks like it spawned "randomly"
        context.scene.frame_set(1)
        self.report({'INFO'}, f"Turntable rig ready: {target.name}, frames 1..{end_f}")
        return {'FINISHED'}


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
        if find_pivot(scene) is None:
            self.report({'ERROR'}, "Create the rig first")
            return {'CANCELLED'}

        end_f = turn_end_frame(props.frames, props.rounds)
        scene.frame_start = 1
        scene.frame_end = end_f
        out = props.output or "//turntable/"
        if not out.endswith(("/", "\\")):
            out += "/"
        scene.render.filepath = out

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

        active = find_pivot(scene) is not None
        row = layout.row()
        row.label(text="Rig active" if active else "No rig",
                  icon='CHECKMARK' if active else 'CANCEL')

        col = layout.column(align=True)
        col.prop(props, "target")
        col.prop(props, "camera")
        col.separator()
        col.prop(props, "frames")
        col.prop(props, "rounds")
        col.prop(props, "radius")
        col.prop(props, "height")
        col.prop(props, "direction")
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
