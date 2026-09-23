"""Run inside Blender on a recipe .blend: apply one known defect (or edit) and save a copy.

Each variant breaks exactly one thing a scene can get wrong without anyone noticing in a
text-only workflow, so the inspector and gates can be tested against real Blender data:

- camera_away: camera turned 180 degrees, so it frames empty backdrop.
- floating: the sculpture is lifted 3 m above its plinth.
- hidden_collection: every mesh moved into a collection with hide_render on.
- zero_scale_parent: every mesh parented to an empty scaled to (0, 0, 0).
- no_lights_unused_emission: lights deleted, world strength 0, and an emissive material
  that no object uses (fake user) - the v1 inspector counted it as illumination.
- relight: a legitimate edit for the preserve-and-relight brief (warmer key, softer fill,
  new camera position); geometry, names and materials stay untouched.
- animated: a valid 48-frame animation (a ring bobs up and down, the camera dollies).
- keys_out_of_range: a ring keyed on frames 300-400 while the scene renders 1-250.
- no_camera / pano_camera / empty: scenes the inspector and `check` must survive (no active
  camera, a panoramic camera, every object deleted).

Usage: blender --background --factory-startup --disable-autoexec recipe.blend
       --python sabotage.py -- OUTPUT.blend VARIANT
"""

import math
import sys

import bpy

VARIANTS = (
    "camera_away",
    "floating",
    "hidden_collection",
    "zero_scale_parent",
    "no_lights_unused_emission",
    "relight",
    "animated",
    "keys_out_of_range",
    "no_camera",
    "pano_camera",
    "empty",
)


def principled(material):
    if bpy.app.version < (5, 0):
        material.use_nodes = True
    return material.node_tree.nodes["Principled BSDF"]


def apply(variant, scene):
    camera = scene.camera
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if variant == "camera_away":
        camera.rotation_euler.z += math.pi
    elif variant == "floating":
        # The sculpture: every mesh except the backdrop and the plinth/platform it stands on.
        movable = [
            o for o in meshes if o.name.startswith(("Copper orbit", "Ceramic", "Sculptural", "Copper"))
        ]
        for obj in movable:
            obj.location.z += 3.0
    elif variant == "hidden_collection":
        hidden = bpy.data.collections.new("Disabled for render")
        scene.collection.children.link(hidden)
        hidden.hide_render = True
        for obj in meshes:
            for collection in list(obj.users_collection):
                collection.objects.unlink(obj)
            hidden.objects.link(obj)
    elif variant == "zero_scale_parent":
        parent = bpy.data.objects.new("Collapsed parent", None)
        scene.collection.objects.link(parent)
        parent.scale = (0, 0, 0)
        for obj in meshes:
            obj.parent = parent
    elif variant == "no_lights_unused_emission":
        for obj in [o for o in scene.objects if o.type == "LIGHT"]:
            bpy.data.objects.remove(obj, do_unlink=True)
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
        glow = bpy.data.materials.new("Unused glow")
        glow.use_fake_user = True
        principled(glow).inputs["Emission Strength"].default_value = 5.0
    elif variant == "relight":
        key = bpy.data.objects["Large warm key"]
        key.data.energy = 1100
        key.data.color = (1.0, 0.78, 0.55)
        fill = bpy.data.objects["Cool fill"]
        fill.data.energy = 250
        fill.data.size = 5
        camera.location = (4.2, -7.6, 3.4)
        target = (0.0, 0.0, 1.2)
        direction = camera.location.copy()
        direction.x, direction.y, direction.z = (target[i] - camera.location[i] for i in range(3))
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    elif variant == "animated":
        scene.frame_start, scene.frame_end = 1, 48
        ring = bpy.data.objects["Copper orbit 3"]
        for frame, lift in ((1, 0.0), (24, 0.5), (48, 0.0)):
            ring.location.z += lift
            ring.keyframe_insert("location", frame=frame)
            ring.location.z -= lift
        camera.keyframe_insert("location", frame=1)
        camera.location.x += 1.0
        camera.keyframe_insert("location", frame=48)
    elif variant == "keys_out_of_range":
        ring = bpy.data.objects["Copper orbit 3"]
        ring.keyframe_insert("rotation_euler", frame=300)
        ring.rotation_euler.z += math.pi
        ring.keyframe_insert("rotation_euler", frame=400)
    elif variant == "no_camera":
        bpy.data.objects.remove(camera, do_unlink=True)
    elif variant == "pano_camera":
        camera.data.type = "PANO"
    elif variant == "empty":
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        raise SystemExit(f"unknown variant {variant!r}; choose from {', '.join(VARIANTS)}")


if __name__ == "__main__":
    output, variant = sys.argv[sys.argv.index("--") + 1 :][:2]
    apply(variant, bpy.context.scene)
    bpy.ops.wm.save_as_mainfile(filepath=output, copy=True)
    print("SABOTAGED=" + output)
