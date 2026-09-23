"""Run inside Blender. Collects facts; does not modify or save the scene."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy

# Blender 5.0 deprecates `use_nodes` (materials and worlds always have node trees).
ALWAYS_NODES = bpy.app.version >= (5, 0)


def uses_nodes(datablock):
    if ALWAYS_NODES:
        return datablock.node_tree is not None
    return datablock.use_nodes


def inspect_scene():
    scene = bpy.context.scene
    objects = []
    for obj in scene.objects:
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "hide_render": obj.hide_render,
                "scale": list(obj.scale),
                "finite": all(math.isfinite(v) for row in obj.matrix_world for v in row),
                "material_count": sum(slot.material is not None for slot in obj.material_slots),
                "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
                "polygons": len(obj.data.polygons) if obj.type == "MESH" else 0,
            }
        )
    missing = []
    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath and not image.packed_file:
            if not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                missing.append(image.name)
    world_light = False
    if scene.world:
        if uses_nodes(scene.world):
            world_light = any(
                node.type == "BACKGROUND"
                and node.inputs["Strength"].default_value > 0
                and max(node.inputs["Color"].default_value[:3]) > 0
                for node in scene.world.node_tree.nodes
            )
        else:
            world_light = max(scene.world.color) > 0
    emitting = False
    for material in bpy.data.materials:
        if uses_nodes(material):
            for node in material.node_tree.nodes:
                if node.type == "EMISSION" and node.inputs["Strength"].default_value > 0:
                    emitting = True
                if node.type == "BSDF_PRINCIPLED" and node.inputs.get("Emission Strength"):
                    emitting |= node.inputs["Emission Strength"].default_value > 0
    return {
        "schema_version": 1,
        "blender_version": bpy.app.version_string,
        "scene": scene.name,
        "camera": scene.camera.name if scene.camera else None,
        "illumination": world_light
        or emitting
        or any(o.type == "LIGHT" and not o.hide_render and o.data.energy > 0 for o in scene.objects),
        "resolution": [
            round(scene.render.resolution_x * scene.render.resolution_percentage / 100),
            round(scene.render.resolution_y * scene.render.resolution_percentage / 100),
        ],
        "engine": scene.render.engine,
        "objects": objects,
        "missing_images": missing,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inspect_scene(), indent=2), encoding="utf-8")
    print("QUALITY_LAB_INSPECTION=" + str(path))
