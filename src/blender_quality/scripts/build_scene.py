"""Deterministic Blender 4.5+ recipes. Use through blender-quality build."""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color, metallic=0, roughness=0.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 75
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.008
    mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    mat.node_tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return mat


def finish(obj, name, mat, bevel=0):
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Soft manufactured edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    if obj.type == "MESH":
        for face in obj.data.polygons:
            face.use_smooth = True
        modifier = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
        modifier.keep_sharp = True
    return obj


def cube(name, location, scale, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat, bevel)


def cylinder(name, location, radius, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=radius, depth=depth, location=location)
    return finish(bpy.context.object, name, mat, 0.025)


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def area(name, location, power, size, color, target):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size, data.color = power, "DISK", size, color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    aim(obj, target)


def build(recipe, output, render=False):
    scene = bpy.data.scenes.new("QualityLab_" + recipe)
    bpy.context.window.scene = scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 960, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Low contrast studio world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.14, 0.18, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.25
    scene.world = world
    ivory = material("Ivory ceramic", (0.68, 0.57, 0.40), roughness=0.24)
    stone = material("Charcoal stone", (0.055, 0.065, 0.075), roughness=0.65)
    copper = material("Brushed copper", (0.63, 0.23, 0.10), metallic=0.8, roughness=0.27)
    walnut = material("Warm walnut", (0.17, 0.07, 0.025), roughness=0.42)
    green = material("Moss textile", (0.12, 0.22, 0.11), roughness=0.9)
    cube("Backdrop floor", (0, 0, -0.09), (200, 200, 0.15), stone, 0)
    target, camera = (0, 0, 1.35), (5, -7, 4)
    if recipe == "product":
        cylinder("Stone plinth", (0, 0, 0.23), 1.12, 0.46, stone)
        cylinder("Ceramic lamp foot", (0, 0, 0.69), 0.36, 0.45, ivory)
        cylinder("Ceramic lamp neck", (0, 0, 1.20), 0.16, 0.65, ivory)
        bpy.ops.mesh.primitive_cone_add(
            vertices=128, radius1=0.90, radius2=0.35, depth=0.72, location=(0, 0, 1.69)
        )
        finish(bpy.context.object, "Sculptural lamp shade", ivory, 0.04)
        cylinder("Copper shade cap", (0, 0, 2.07), 0.12, 0.07, copper)
    elif recipe == "abstract":
        cube("Exhibition plinth", (0, 0, 0.30), (2.4, 1.8, 0.6), stone)
        for index in range(3):
            bpy.ops.mesh.primitive_torus_add(
                major_segments=96,
                minor_segments=32,
                location=((index - 1) * 0.46, 0, 1.48 + index * 0.16),
                major_radius=0.65,
                minor_radius=0.15,
            )
            obj = bpy.context.object
            obj.rotation_euler = (math.pi / 2, (index - 1) * 0.4, (index - 1) * 0.5)
            finish(obj, "Copper orbit " + str(index + 1), copper)
        bpy.context.view_layer.update()
        rings = [obj for obj in scene.objects if obj.name.startswith("Copper orbit")]
        bottom = min((obj.matrix_world @ vertex.co).z for obj in rings for vertex in obj.data.vertices)
        for obj in rings:
            obj.location.z += 0.602 - bottom
    else:
        target, camera = (0, 0.1, 1.15), (5, -7, 5)
        cube("Walnut platform", (0, 0, 0.06), (4, 3.5, 0.12), walnut)
        cube("Back wall", (0, 1.7, 1.6), (4, 0.12, 3.2), ivory)
        cube("Side wall", (-1.95, 0.2, 1.6), (0.12, 3, 3.2), ivory)
        cube("Chair seat", (0, -0.35, 0.68), (1.1, 1.1, 0.25), green, 0.12)
        cube("Chair back", (0, 0.14, 1.18), (1.1, 0.22, 1.0), green, 0.10)
        for x in [-0.42, 0.42]:
            for y in [-0.75, 0.0]:
                cube("Chair leg", (x, y, 0.32), (0.1, 0.1, 0.55), walnut, 0.015)
        for z in [0.7, 1.4, 2.1]:
            cube("Floating shelf", (-1.0, 1.35, z), (1.5, 0.48, 0.08), walnut, 0.01)
            for index in range(5):
                cube(
                    "Book",
                    (-1.58 + index * 0.17, 1.33, z + 0.24),
                    (0.12, 0.26, 0.4 + (index % 2) * 0.08),
                    green if index % 2 else copper,
                    0.005,
                )
        cylinder("Side table base", (1.05, 0.10, 0.42), 0.16, 0.72, walnut)
        cylinder("Side table top", (1.05, 0.10, 0.81), 0.47, 0.08, walnut)
        cylinder("Reading lamp stem", (1.30, 1.05, 0.80), 0.045, 1.5, copper)
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=48, ring_count=24, radius=0.32, location=(1.30, 1.05, 1.65)
        )
        finish(bpy.context.object, "Paper lamp", ivory)
    camera_data = bpy.data.cameras.new("Editorial camera")
    camera_obj = bpy.data.objects.new("Editorial camera", camera_data)
    scene.collection.objects.link(camera_obj)
    camera_obj.location = camera
    camera_data.lens = 55
    aim(camera_obj, target)
    scene.camera = camera_obj
    area("Large warm key", (-3, -4, 6), 900, 4, (1.0, 0.85, 0.65), target)
    area("Cool fill", (4, -1, 3), 400, 3, (0.65, 0.78, 1.0), target)
    area("Edge separation", (1, 4, 5), 1000, 2, (1.0, 0.67, 0.40), target)
    output.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str((output / (recipe + ".png")).resolve())
    bpy.ops.wm.save_as_mainfile(filepath=str((output / (recipe + ".blend")).resolve()))
    if render:
        bpy.ops.render.render(write_still=True)
    print("QUALITY_LAB_SCENE=" + str(output / (recipe + ".blend")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", choices=["product", "abstract", "interior"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    build(args.recipe, args.output, args.render)
