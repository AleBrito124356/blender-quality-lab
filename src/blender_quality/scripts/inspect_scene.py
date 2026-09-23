"""Run inside Blender 4.5+ (verified on 5.2 LTS). Collect scene facts; never save the .blend.

`blender-quality inspect` starts Blender with --background --factory-startup --disable-autoexec and
runs this script, which writes inspection schema v2. The facts are computed from geometry, not from
pixels, so a model or reviewer without vision can tell what the camera sees, what is cut off or
hidden, what floats, which lights actually reach the subject and what is animated.

The scene is changed only in memory and never saved: render visibility is mirrored into the viewport
depsgraph so the evaluated geometry (modifiers, instances, geometry nodes) matches what renders.
"""

import argparse
import fnmatch
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SCHEMA_VERSION = 2
ALWAYS_NODES = bpy.app.version >= (5, 0)  # Blender 5 deprecates use_nodes; node trees always exist
SAMPLES = 256  # area-weighted surface samples per object
OCCLUSION_RAYS = 96  # camera rays per object for the hidden-behind check
GRID_COLUMNS = 64
MAX_RAY_TRIANGLES = 4_000_000
CONTACT_TOLERANCE_M = 0.005
ANIMATION_SAMPLES = 24
ID_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
SEE_THROUGH_NODES = {"BSDF_GLASS", "BSDF_REFRACTION", "BSDF_TRANSPARENT", "BSDF_TRANSLUCENT", "HOLDOUT"}
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}


# ---------------------------------------------------------------- small helpers


def num(value, digits=4):
    value = float(value)
    return round(value, digits) if math.isfinite(value) else None


def vec(values, digits=4):
    return [num(v, digits) for v in values]


def luminance(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def angle_deg(a, b):
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a, b)) / (na * nb)))))


def safe_set(block, attr, value):
    try:
        if getattr(block, attr) != value:
            setattr(block, attr, value)
    except (AttributeError, RuntimeError, TypeError):
        pass  # linked or override data cannot be changed; it keeps its viewport state


def uses_nodes(block):
    if block is None or getattr(block, "node_tree", None) is None:
        return False
    return True if ALWAYS_NODES else bool(block.use_nodes)


def clean(value):
    """Replace non-finite floats so the JSON stays valid."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    return value


# ---------------------------------------------------------------- shader graphs


def reachable_nodes(tree):
    """Nodes that feed the active output (so they affect the render), including node group contents."""
    if tree is None:
        return []
    output = None
    for target in ("CYCLES", "ALL"):
        try:
            output = output or tree.get_output_node(target)
        except (AttributeError, TypeError, RuntimeError):
            pass
    if output is None:
        outputs = [n for n in tree.nodes if n.type in {"OUTPUT_MATERIAL", "OUTPUT_WORLD"}]
        output = next((n for n in outputs if getattr(n, "is_active_output", False)), None)
        output = output or (outputs[0] if outputs else None)
    if output is None:
        return []
    found, seen, stack = [], set(), [output]
    while stack:
        node = stack.pop()
        if node.as_pointer() in seen:
            continue
        seen.add(node.as_pointer())
        found.append(node)
        for socket in node.inputs:
            for link in socket.links:
                if not getattr(link, "is_muted", False):
                    stack.append(link.from_node)
        if node.type == "GROUP" and node.node_tree is not None:
            found += [n for n in node.node_tree.nodes if n.type != "GROUP_OUTPUT"]
    return found


def socket_value(node, *names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is None:
            continue
        if socket.is_linked:
            return "linked"
        value = socket.default_value
        try:
            return tuple(value)
        except TypeError:
            return float(value)
    return None


def emission_of(node):
    if node.type == "EMISSION":
        strength, color = socket_value(node, "Strength"), socket_value(node, "Color")
    elif node.type == "BSDF_PRINCIPLED":
        strength = socket_value(node, "Emission Strength")
        color = socket_value(node, "Emission Color", "Emission")
    else:
        return None
    if strength is None or color is None or strength == 0.0:
        return None
    if "linked" in (strength, color):
        return {
            "strength": None if strength == "linked" else num(strength),
            "textured": True,
            "radiance": None,
        }
    radiance = strength * luminance(color)
    if radiance <= 0:
        return None
    return {"strength": num(strength), "color": vec(color[:3]), "textured": False, "radiance": num(radiance)}


def material_facts(mat):
    facts = {"name": mat.name, "shaders": [], "emission": None, "see_through": False, "images": []}
    if not uses_nodes(mat):
        facts.update(base_color=vec(mat.diffuse_color[:3]), shaders=["NO_NODES"])
        return facts
    nodes = reachable_nodes(mat.node_tree)
    facts["shaders"] = sorted({n.type for n in nodes if n.type.startswith(("BSDF_", "EMISSION", "HOLDOUT"))})
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if principled is not None:
        base = socket_value(principled, "Base Color")
        facts["base_color"] = "texture" if base == "linked" else vec(base[:3])
        for key, names in {
            "metallic": ("Metallic",),
            "roughness": ("Roughness",),
            "transmission": ("Transmission Weight", "Transmission"),
            "alpha": ("Alpha",),
        }.items():
            value = socket_value(principled, *names)
            facts[key] = "texture" if value == "linked" else (num(value) if value is not None else None)
        transmission, alpha = facts.get("transmission"), facts.get("alpha")
        if isinstance(transmission, float) and transmission > 0.5:
            facts["see_through"] = True
        if alpha == "texture" or (isinstance(alpha, float) and alpha < 0.5):
            facts["see_through"] = True
    if any(n.type in SEE_THROUGH_NODES for n in nodes):
        facts["see_through"] = True
    emissions = [e for e in (emission_of(n) for n in nodes) if e]
    if emissions:
        facts["emission"] = max(emissions, key=lambda e: math.inf if e["radiance"] is None else e["radiance"])
    facts["images"] = sorted({n.image.name for n in nodes if n.type == "TEX_IMAGE" and n.image is not None})
    return facts


def world_facts(scene):
    world = scene.world
    facts = {"name": None, "strength": 0.0, "color": [0.0, 0.0, 0.0], "textured": False, "radiance": 0.0}
    facts["film_transparent"] = bool(scene.render.film_transparent)
    if world is None:
        return facts
    facts["name"] = world.name
    if not uses_nodes(world):
        facts.update(strength=1.0, color=vec(world.color[:3]), radiance=num(luminance(world.color)))
        return facts
    nodes = reachable_nodes(world.node_tree)
    radiance, strength, textured, color = 0.0, 0.0, False, [0.0, 0.0, 0.0]
    for node in (n for n in nodes if n.type == "BACKGROUND"):
        s, c = socket_value(node, "Strength"), socket_value(node, "Color")
        if s == "linked" or c == "linked":
            textured = True
            strength = max(strength, 1.0 if s == "linked" else s)
            continue
        strength = max(strength, s)
        if s * luminance(c) >= radiance:
            radiance, color = s * luminance(c), list(c[:3])
    facts.update(
        strength=num(strength),
        color=vec(color),
        textured=textured,
        textures=sorted({n.type for n in nodes if n.type in {"TEX_ENVIRONMENT", "TEX_SKY", "TEX_IMAGE"}}),
        radiance=None if textured else num(radiance),
    )
    return facts


# ---------------------------------------------------------------- visibility


def collection_paths(view_layer):
    """Every path from the view layer root to each collection, with its render state."""
    paths = {}

    def walk(layer, excluded, hidden, holdout, indirect):
        coll = layer.collection
        excluded = excluded or layer.exclude
        hidden = hidden + ([coll.name] if getattr(coll, "hide_render", False) else [])
        holdout = holdout or layer.holdout
        indirect = indirect or layer.indirect_only
        state = {
            "name": coll.name,
            "excluded": excluded,
            "hidden": hidden,
            "holdout": holdout,
            "indirect": indirect,
        }
        paths.setdefault(coll.as_pointer(), []).append(state)
        for child in layer.children:
            walk(child, excluded, hidden, holdout, indirect)

    walk(view_layer.layer_collection, False, [], False, False)
    return paths


def visibility(obj, paths, view_layer):
    """(reasons it does not render, reasons the camera cannot see it)."""
    reasons, camera_reasons = [], []
    states = [s for coll in obj.users_collection for s in paths.get(coll.as_pointer(), [])]
    usable = [s for s in states if not s["excluded"] and not s["hidden"]]
    if obj.hide_render:
        reasons.append("object has hide_render on")
    if not states:
        reasons.append(f"not linked into view layer '{view_layer.name}'")
    elif not usable:
        state = states[0]
        if state["excluded"]:
            reasons.append(f"collection '{state['name']}' is excluded from view layer '{view_layer.name}'")
        if state["hidden"]:
            reasons.append(f"collection '{state['hidden'][0]}' has hide_render on")
    parent = obj.parent
    if parent is not None and parent.instance_type in {"VERTS", "FACES"}:
        reasons.append(
            f"instanced by parent '{parent.name}' ({parent.instance_type}); the original is not rendered"
        )
    if obj.type not in GEOMETRY_TYPES and obj.type != "EMPTY":
        return reasons, camera_reasons  # lights and cameras are not meant to be seen by the camera
    if not getattr(obj, "visible_camera", True):
        camera_reasons.append("camera ray visibility is off")
    if getattr(obj, "is_holdout", False):
        camera_reasons.append("object is a holdout")
    if usable and all(s["holdout"] for s in usable):
        camera_reasons.append("collection is a holdout")
    if usable and all(s["indirect"] for s in usable):
        camera_reasons.append("collection is indirect-only")
    return reasons, camera_reasons


def mirror_render_visibility(scene, view_layer):
    """Make the viewport depsgraph evaluate what the render would (in memory only)."""
    for coll in bpy.data.collections:
        safe_set(coll, "hide_viewport", bool(getattr(coll, "hide_render", False)))

    def unhide(layer):
        safe_set(layer, "hide_viewport", False)
        for child in layer.children:
            unhide(child)

    unhide(view_layer.layer_collection)
    for obj in scene.objects:
        safe_set(obj, "hide_viewport", obj.hide_render)
        try:
            obj.hide_set(False, view_layer=view_layer)
        except (RuntimeError, TypeError):
            pass
        if hasattr(obj, "show_instancer_for_render"):
            safe_set(obj, "show_instancer_for_viewport", obj.show_instancer_for_render)
        for modifier in obj.modifiers:
            safe_set(modifier, "show_viewport", modifier.show_render)


# ---------------------------------------------------------------- geometry


def new_owner():
    return {
        "parts": [],
        "vertices": 0,
        "polygons": 0,
        "triangles": 0,
        "instances": 0,
        "materials": set(),
        "unassigned": 0,
        "min": np.full(3, np.inf),
        "max": np.full(3, -np.inf),
        "finite": True,
        "truncated": False,
    }


def collect_geometry(depsgraph):
    """World-space triangles per owner object, from what the depsgraph would render."""
    owners, cache, budget = {}, {}, MAX_RAY_TRIANGLES
    for dup in depsgraph.object_instances:
        ob = dup.object
        if ob.type != "MESH":
            continue
        owner_ob = dup.parent if dup.is_instance and dup.parent is not None else ob
        name = owner_ob.original.name
        mesh = ob.data
        key = (mesh.as_pointer(), ob.original.name)
        entry = cache.get(key)
        if entry is None:
            co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", co)
            tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", tris)
            material_index = np.empty(len(mesh.polygons), dtype=np.int32)
            mesh.polygons.foreach_get("material_index", material_index)
            slots = [slot.material.name if slot.material else None for slot in ob.material_slots]
            used, unassigned = set(), 0
            for slot_index, count in zip(*np.unique(material_index, return_counts=True)):
                slot = slots[slot_index] if 0 <= slot_index < len(slots) else None
                if slot:
                    used.add(slot)
                else:
                    unassigned += int(count)
            entry = (
                co.reshape(-1, 3).astype(np.float64),
                tris.reshape(-1, 3),
                len(mesh.polygons),
                used,
                unassigned,
            )
            cache[key] = entry
        co, tris, polygons, used, unassigned = entry
        matrix = np.array(dup.matrix_world, dtype=np.float64)
        world = co @ matrix[:3, :3].T + matrix[:3, 3]
        rec = owners.setdefault(name, new_owner())
        rec["instances"] += 1
        rec["vertices"] += len(co)
        rec["polygons"] += polygons
        rec["triangles"] += len(tris)
        rec["materials"] |= used
        rec["unassigned"] += unassigned
        if len(world):
            finite = bool(np.isfinite(world).all())
            rec["finite"] &= finite
            if finite:
                rec["min"] = np.minimum(rec["min"], world.min(axis=0))
                rec["max"] = np.maximum(rec["max"], world.max(axis=0))
        if not rec["finite"]:
            continue
        if len(tris) <= budget:
            rec["parts"].append((world, tris))
            budget -= len(tris)
        else:
            rec["truncated"] = True
    return owners


def owner_arrays(rec):
    if not rec["parts"]:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    verts, tris, offset = [], [], 0
    for world, t in rec["parts"]:
        verts.append(world)
        tris.append(t.astype(np.int64) + offset)
        offset += len(world)
    return np.concatenate(verts), np.concatenate(tris)


def surface_samples(verts, tris, count, seed):
    """Area-weighted random points (and face normals) on the triangles; deterministic per object."""
    empty = np.zeros((0, 3)), np.zeros((0, 3)), 0.0
    if len(tris) == 0:
        return empty
    p0, p1, p2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    doubled = np.linalg.norm(cross, axis=1)
    total = float(doubled.sum())
    if not math.isfinite(total) or total <= 1e-18:
        return empty
    rng = np.random.default_rng(seed)
    index = np.clip(np.searchsorted(np.cumsum(doubled) / total, rng.random(count)), 0, len(tris) - 1)
    r1, r2 = np.sqrt(rng.random(count))[:, None], rng.random(count)[:, None]
    points = (1 - r1) * p0[index] + r1 * (1 - r2) * p1[index] + r1 * r2 * p2[index]
    normals = cross[index] / np.maximum(doubled[index], 1e-30)[:, None]
    return points, normals, total / 2


def mesh_hash(mesh, cache):
    """Fingerprint of the original mesh data (vertex positions rounded to 1e-5 and face topology)."""
    if mesh.name_full not in cache:
        co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", co)
        loops = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loops)
        digest = hashlib.sha1(np.round(co.astype(np.float64), 5).tobytes())
        digest.update(loops.tobytes())
        cache[mesh.name_full] = digest.hexdigest()[:16]
    return cache[mesh.name_full]


class SceneRays:
    """One BVH over every render-visible triangle, remembering which object owns each triangle."""

    def __init__(self, owners, names, scale):
        self.names = names
        self.eps = max(1e-7, 1e-6 * scale)
        verts, tris, owner_index, offset = [], [], [], 0
        for index, name in enumerate(names):
            v, t = owner_arrays(owners[name])
            if len(t) == 0:
                continue
            verts.append(v)
            tris.append(t + offset)
            owner_index.append(np.full(len(t), index, dtype=np.int32))
            offset += len(v)
        self.tree = None
        if tris:
            self.owner_of = np.concatenate(owner_index)
            self.tree = BVHTree.FromPolygons(
                np.concatenate(verts).tolist(), np.concatenate(tris).tolist(), all_triangles=True
            )

    def first(self, origin, direction, distance, skip=frozenset()):
        """First hit (owner index, distance, normal) along a ray, passing through skipped owners."""
        if self.tree is None:
            return None
        origin, direction = Vector(origin), Vector(direction).normalized()
        travelled = 0.0
        for _ in range(64):
            if distance - travelled <= 0:
                return None
            loc, normal, index, dist = self.tree.ray_cast(origin, direction, distance - travelled)
            if loc is None:
                return None
            owner = int(self.owner_of[index])
            travelled += dist
            if owner not in skip:
                return owner, travelled, normal
            origin = loc + direction * self.eps
            travelled += self.eps
        return None


# ---------------------------------------------------------------- camera


class CameraModel:
    """Projection matching bpy_extras.object_utils.world_to_camera_view, vectorised with numpy."""

    def __init__(self, scene, obj):
        data = obj.data
        self.obj, self.type = obj, data.type
        matrix = obj.matrix_world.normalized()
        self.origin = np.array(matrix.translation, dtype=np.float64)
        self.rot = np.array(matrix.to_3x3(), dtype=np.float64)
        self.right, self.up, self.forward = self.rot[:, 0], self.rot[:, 1], -self.rot[:, 2]
        frame = [Vector(v) for v in data.view_frame(scene=scene)]
        xs, ys = [v.x for v in frame], [v.y for v in frame]
        self.min_x, self.max_x, self.min_y, self.max_y = min(xs), max(xs), min(ys), max(ys)
        self.depth = -frame[0].z
        self.clip_start, self.clip_end = data.clip_start, data.clip_end
        self.ortho = data.type == "ORTHO"

    def fov_deg(self):
        if self.ortho:
            return None, None
        return (
            math.degrees(2 * math.atan((self.max_x - self.min_x) / 2 / self.depth)),
            math.degrees(2 * math.atan((self.max_y - self.min_y) / 2 / self.depth)),
        )

    def project(self, points):
        """Normalized frame coordinates (x right, y up, 0..1 inside) and depth along the view axis."""
        local = (points - self.origin) @ self.rot
        z = -local[:, 2]
        if self.ortho:
            u, v = local[:, 0], local[:, 1]
        else:
            safe = np.where(np.abs(z) < 1e-12, 1e-12, z)
            u, v = local[:, 0] * self.depth / safe, local[:, 1] * self.depth / safe
        x = (u - self.min_x) / (self.max_x - self.min_x)
        y = (v - self.min_y) / (self.max_y - self.min_y)
        return x, y, z

    def inside(self, x, y, z):
        return (z > self.clip_start) & (z < self.clip_end) & (x >= 0) & (x <= 1) & (y >= 0) & (y <= 1)

    def pixel_ray(self, x, y):
        u = self.min_x + x * (self.max_x - self.min_x)
        v = self.min_y + y * (self.max_y - self.min_y)
        if self.ortho:
            origin = self.origin + self.rot @ np.array([u, v, 0.0])
            return origin, self.forward, self.clip_start, self.clip_end
        local = np.array([u, v, -self.depth])
        length = float(np.linalg.norm(local))
        cos = self.depth / length
        return self.origin, self.rot @ (local / length), self.clip_start / cos, self.clip_end / cos

    def ray_to(self, point):
        if self.ortho:
            local = (point - self.origin) @ self.rot
            origin = self.origin + self.rot @ np.array([local[0], local[1], 0.0])
            return origin, self.forward, float(-local[2])
        delta = point - self.origin
        distance = float(np.linalg.norm(delta))
        return self.origin, delta / max(distance, 1e-12), distance

    def facts(self):
        data = self.obj.data
        hfov, vfov = self.fov_deg()
        dof = data.dof
        return {
            "name": self.obj.name,
            "type": data.type,
            "lens_mm": num(data.lens),
            "ortho_scale": num(data.ortho_scale) if self.ortho else None,
            "sensor_mm": [num(data.sensor_width), num(data.sensor_height)],
            "sensor_fit": data.sensor_fit,
            "shift": [num(data.shift_x), num(data.shift_y)],
            "clip": [num(data.clip_start, 6), num(data.clip_end)],
            "location": vec(self.origin),
            "rotation_euler": vec(self.obj.rotation_euler),
            "rotation_mode": self.obj.rotation_mode,
            "forward": vec(self.forward),
            "up": vec(self.up),
            "right": vec(self.right),
            "hfov_deg": num(hfov, 2) if hfov else None,
            "vfov_deg": num(vfov, 2) if vfov else None,
            "dof": {
                "use": bool(dof.use_dof),
                "focus_distance": num(dof.focus_distance),
                "focus_object": dof.focus_object.name if dof.focus_object else None,
                "fstop": num(dof.aperture_fstop),
            },
        }


# ---------------------------------------------------------------- analysis passes


def collection_ancestors(collection):
    found = []
    for parent in bpy.data.collections:
        if collection.name in parent.children:
            found += [parent, *collection_ancestors(parent)]
    return found


def choose_subject(owners, candidates, patterns, collections, camera):
    """Subject objects by --subject/--subject-collection, else everything except large backdrops."""
    if patterns or collections:
        wanted = []
        for name in candidates:
            obj = bpy.data.objects.get(name)
            in_collection = obj is not None and any(
                c.name in collections or any(a.name in collections for a in collection_ancestors(c))
                for c in obj.users_collection
            )
            if in_collection or any(fnmatch.fnmatchcase(name, p) for p in patterns):
                wanted.append(name)
        return wanted, [n for n in candidates if n not in wanted], "names"
    if not candidates:
        return [], [], "heuristic"
    largest = {n: float((owners[n]["max"] - owners[n]["min"]).max()) for n in candidates}
    smallest = {n: float((owners[n]["max"] - owners[n]["min"]).min()) for n in candidates}
    flat = {n: smallest[n] <= 0.05 * largest[n] for n in candidates}
    reference = float(np.median([largest[n] for n in candidates if not flat[n]] or list(largest.values())))
    environment = []
    for name in candidates:
        big = largest[name] >= 4 * reference
        encloses_camera = camera is not None and bool(
            np.all(owners[name]["min"] <= camera.origin) and np.all(camera.origin <= owners[name]["max"])
        )
        if (flat[name] and big) or largest[name] >= 20 * reference or (encloses_camera and big):
            environment.append(name)
    subject = [n for n in candidates if n not in environment]
    if not subject:
        return list(candidates), [], "heuristic"
    return subject, environment, "heuristic"


def coverage_grid(camera, rays, hidden_from_camera, columns, aspect):
    """A low-resolution 'object ID pass': the first visible object behind each grid cell."""
    rows = max(4, int(round(columns / aspect)))
    grid, counts, backfaces = [], Counter(), Counter()
    for j in range(rows):
        y = 1 - (j + 0.5) / rows
        row = []
        for i in range(columns):
            origin, direction, t0, t1 = camera.pixel_ray((i + 0.5) / columns, y)
            hit = rays.first(origin + direction * t0, direction, t1 - t0, hidden_from_camera)
            if hit is None:
                row.append(-1)
                continue
            owner, _dist, normal = hit
            row.append(owner)
            counts[owner] += 1
            if normal.dot(Vector(direction)) > 0:
                backfaces[owner] += 1
        grid.append(row)
    return grid, counts, backfaces, rows


def encode_grid(grid, counts, names):
    legend, char_of = {}, {}
    for position, (owner, _count) in enumerate(counts.most_common()):
        char = ID_CHARS[position] if position < len(ID_CHARS) else "#"
        char_of[owner] = char
        if char != "#":
            legend[char] = names[owner]
    return legend, ["".join("." if o < 0 else char_of[o] for o in row) for row in grid]


def camera_view(camera, rays, owner_index, points, normals, verts, hidden_from_camera):
    """What the camera sees of one object: frame share, cut-off edges, occlusion, depth."""
    seen = np.zeros(len(points), dtype=bool)
    flipped = normals.copy()
    if len(points) == 0:
        return {"in_frame": None, "note": "degenerate: no surface area to sample"}, seen, flipped
    x, y, z = camera.project(points)
    inside = camera.inside(x, y, z)
    in_front = z > camera.clip_start
    view = {
        "in_frame": num(inside.mean()),
        "behind_camera": bool((z <= 0).all()),
        "beyond_clip_end": num(((z >= camera.clip_end) & in_front).mean()),
    }
    vx, vy, vz = camera.project(verts)
    front = vz > camera.clip_start
    if front.any():
        sx, sy = np.clip(vx[front], -2, 3), np.clip(vy[front], -2, 3)
        view["screen_bbox"] = vec([sx.min(), sy.min(), sx.max(), sy.max()], 3)
        if inside.any():
            view["cut_off"] = [
                edge
                for edge, hit in (
                    ("left", sx.min() < -0.001),
                    ("right", sx.max() > 1.001),
                    ("bottom", sy.min() < -0.001),
                    ("top", sy.max() > 1.001),
                )
                if hit
            ]
    center = (verts.min(axis=0) + verts.max(axis=0)) / 2
    cx, cy, cz = camera.project(center[None, :])
    view["center"] = vec([cx[0], cy[0]], 3) if cz[0] > 0 else None
    view["distance"] = num(np.linalg.norm(center - camera.origin))
    candidates = np.flatnonzero(inside)
    if rays.tree is None or len(candidates) == 0:
        return view, seen, flipped
    tested = candidates[:: max(1, len(candidates) // OCCLUSION_RAYS)]
    occluded, blockers = 0, Counter()
    for i in tested:
        origin, direction, distance = camera.ray_to(points[i])
        hit = rays.first(origin, direction, distance + rays.eps, hidden_from_camera)
        tolerance = max(10 * rays.eps, 1e-4 * distance)
        if hit is None or hit[1] >= distance - tolerance:
            seen[i] = True
            if np.dot(flipped[i], camera.origin - points[i]) < 0:
                flipped[i] = -flipped[i]  # two-sided surfaces: shade the side the camera sees
        elif hit[0] != owner_index:
            occluded += 1
            blockers[hit[0]] += 1
    view["occluded"] = num(occluded / len(tested))
    view["occluded_by"] = [rays.names[o] for o, _ in blockers.most_common(3)]
    view["seen"] = num(seen[tested].mean())
    return view, seen, flipped


def contact_analysis(owners, names, rays, tolerance_bu):
    """Which objects touch, and which groups rest on nothing: floating groups and their gap below."""
    geo = {}
    for name in names:
        verts, tris = owner_arrays(owners[name])
        if len(tris):
            size = float((owners[name]["max"] - owners[name]["min"]).max())
            geo[name] = {"verts": verts, "tris": tris, "size": size, "tree": None}
    index = {name: i for i, name in enumerate(rays.names)}

    def tree(name):
        g = geo[name]
        if g["tree"] is None:
            g["tree"] = BVHTree.FromPolygons(g["verts"].tolist(), g["tris"].tolist(), all_triangles=True)
        return g["tree"]

    def lowest(name):
        verts = geo[name]["verts"]
        low = verts[verts[:, 2] <= verts[:, 2].min() + max(tolerance_bu, 0.02 * geo[name]["size"])]
        return low[:: max(1, len(low) // 24)]

    def probes(name):
        verts = geo[name]["verts"]
        return np.concatenate([verts[:: max(1, len(verts) // 128)], lowest(name), owners[name]["samples"]])

    def within(other_tree, points, tol):
        for p in points:
            if other_tree.find_nearest(Vector(p), tol)[0] is not None:
                return True
        return False

    touching = {name: {} for name in geo}
    listed = list(geo)
    for i, a in enumerate(listed):
        for b in listed[i + 1 :]:
            tol = min(tolerance_bu, max(0.02 * min(geo[a]["size"], geo[b]["size"]), 1e-6))
            if np.any(owners[a]["max"] + tol < owners[b]["min"]) or np.any(
                owners[b]["max"] + tol < owners[a]["min"]
            ):
                continue
            kind = None
            if tree(a).overlap(tree(b)):
                kind = "intersects"
            elif within(tree(b), probes(a), tol) or within(tree(a), probes(b), tol):
                kind = "touches"
            if kind:
                touching[a][b] = touching[b][a] = kind

    def gap_below(members):
        best, surface = None, None
        skip = frozenset(index[m] for m in members)
        lift = rays.eps * 10
        for name in members:
            for p in lowest(name):
                hit = rays.first(Vector(p) + Vector((0, 0, lift)), (0, 0, -1), 1e9, skip)
                if hit is not None and (best is None or hit[1] - lift < best):
                    best, surface = max(0.0, hit[1] - lift), rays.names[hit[0]]
        return best, surface

    below = {name: gap_below([name]) for name in geo}
    parent = {name: name for name in geo}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for a, others in touching.items():
        for b in others:
            parent[find(a)] = find(b)
    groups = {}
    for name in geo:
        groups.setdefault(find(name), []).append(name)
    floating = []
    for members in groups.values():
        if any(below[m][0] is None for m in members):
            continue  # rests on nothing measurable: the ground itself, or over empty space
        gap, surface = gap_below(members)
        tol = min(tolerance_bu, max(0.02 * max(geo[m]["size"] for m in members), 1e-6))
        if gap is not None and gap > tol:
            floating.append({"objects": sorted(members), "gap": num(gap), "above": surface})
    floating_names = {m for group in floating for m in group["objects"]}
    support = {
        name: {
            "touching": sorted(touching[name]),
            "intersecting": sorted(n for n, k in touching[name].items() if k == "intersects"),
            "gap_below": num(below[name][0]) if below[name][0] is not None else None,
            "surface_below": below[name][1],
            "floating": name in floating_names,
        }
        for name in geo
    }
    return support, sorted(floating, key=lambda g: -g["gap"])


def light_analysis(lights, basis, rays, shadow_skip, subject_center, camera):
    """For each light: is it aimed at the subject, does it reach it, and roughly how strongly."""
    points, normals, weights = basis
    results = []
    for obj, hidden_reasons in lights:
        data = obj.data
        matrix = obj.matrix_world
        location = np.array(matrix.translation, dtype=np.float64)
        forward = -np.array(matrix.to_3x3().normalized().col[2], dtype=np.float64)
        power = float(data.energy) * 2 ** float(getattr(data, "exposure", 0.0))
        color_lum = luminance(data.color)
        fact = {
            "name": obj.name,
            "type": data.type,
            "energy": num(data.energy),
            "exposure": num(getattr(data, "exposure", 0.0)),
            "color": vec(data.color),
            "use_temperature": bool(getattr(data, "use_temperature", False)),
            "render_visible": not hidden_reasons,
            "hidden_by": hidden_reasons,
            "location": vec(location),
            "direction": vec(forward),
            "cast_shadows": bool(getattr(data, "use_shadow", True)),
        }
        if data.type == "SPOT":
            fact["spot_size_deg"] = num(math.degrees(data.spot_size), 2)
        elif data.type == "AREA":
            fact.update(shape=data.shape, size=num(data.size), spread_deg=num(math.degrees(data.spread), 2))
            fact["normalize"] = bool(getattr(data, "normalize", True))
        elif data.type == "SUN":
            fact["angle_deg"] = num(math.degrees(data.angle), 2)
        aimed = None
        if subject_center is not None:
            to_subject = subject_center - location
            fact["distance_to_subject"] = num(np.linalg.norm(to_subject))
            aimed = True
            if data.type in {"SPOT", "AREA"}:
                off_axis = angle_deg(forward, to_subject) or 0.0
                fact["angle_off_axis_deg"] = num(off_axis, 2)
                if data.type == "SPOT":
                    aimed = off_axis <= math.degrees(data.spot_size) / 2 + 5
                else:
                    aimed = off_axis < min(90.0, math.degrees(data.spread) / 2 + 5)
            if camera is not None:
                toward_light = -forward if data.type == "SUN" else location - subject_center
                fact["angle_to_camera_deg"] = num(angle_deg(toward_light, camera.origin - subject_center), 2)
        fact["aimed_at_subject"] = aimed
        if len(points) == 0 or not fact["render_visible"] or power <= 0 or color_lum <= 0:
            fact.update(reaches_subject=None if len(points) == 0 else 0.0, irradiance=0.0)
            results.append(fact)
            continue
        area_factor = 1.0
        if data.type == "AREA" and not fact["normalize"]:
            sy = data.size_y if data.shape in {"RECTANGLE", "ELLIPSE"} else data.size
            area_factor = data.size * sy * (math.pi / 4 if data.shape in {"DISK", "ELLIPSE"} else 1.0)
        half_cone = math.degrees(data.spot_size) / 2 if data.type == "SPOT" else None
        half_spread = math.degrees(data.spread) / 2 if data.type == "AREA" else None
        lit = blocked = irradiance = 0.0
        blockers = Counter()
        for p, n, w in zip(points, normals, weights):
            if data.type == "SUN":
                to_light, dist = -forward, 1e7
            else:
                to_light = location - p
                dist = float(np.linalg.norm(to_light))
                if dist < 1e-9:
                    continue
                to_light = to_light / dist
            ndotl = float(np.dot(n, to_light))
            if ndotl <= 0:
                continue
            cos_light = float(np.dot(forward, -to_light))
            if half_cone is not None and math.degrees(math.acos(max(-1.0, min(1.0, cos_light)))) > half_cone:
                continue
            if half_spread is not None and (
                cos_light <= 0 or math.degrees(math.acos(min(1.0, cos_light))) > half_spread
            ):
                continue
            if fact["cast_shadows"]:
                hit = rays.first(p + n * rays.eps * 20, to_light, dist - rays.eps * 40, shadow_skip)
                if hit is not None:
                    blocked += w
                    blockers[hit[0]] += 1
                    continue
            lit += w
            if data.type == "SUN":
                e = power * ndotl
            elif data.type == "AREA":
                e = power * area_factor * cos_light * ndotl / (math.pi * dist * dist)
            else:
                e = power * ndotl / (4 * math.pi * dist * dist)
            irradiance += w * e * color_lum
        total = float(weights.sum())
        fact["reaches_subject"] = num(lit / total)
        fact["facing_but_blocked"] = num(blocked / total)
        fact["blocked_by"] = [rays.names[o] for o, _ in blockers.most_common(3)]
        fact["irradiance"] = num(irradiance / total)
        results.append(fact)
    return results


def fcurves_of(id_block):
    """(fcurves, NLA strip ranges) for an ID: layered actions on Blender 4.4+/5.x, legacy fcurves before."""
    anim = getattr(id_block, "animation_data", None)
    if anim is None:
        return [], []
    curves, nla_ranges, actions = [], [], []
    if anim.action is not None:
        actions.append((anim.action, getattr(anim, "action_slot", None)))
    for track in anim.nla_tracks:
        if track.mute:
            continue
        for strip in track.strips:
            if strip.action is not None and not strip.mute:
                actions.append((strip.action, getattr(strip, "action_slot", None)))
                nla_ranges.append((strip.frame_start, strip.frame_end))
    for action, slot in actions:
        layers = getattr(action, "layers", None)
        if layers is not None and len(layers):
            for layer in layers:
                for strip in layer.strips:
                    if slot is not None:
                        try:
                            bags = [strip.channelbag(slot)]
                        except (TypeError, RuntimeError):
                            bags = []
                    else:
                        bags = list(getattr(strip, "channelbags", []))
                    for bag in bags:
                        if bag is not None:
                            curves += list(bag.fcurves)
        elif hasattr(action, "fcurves"):  # Blender < 4.4 (removed in 5.0)
            curves += list(action.fcurves)
    return curves, nla_ranges


def animation_facts(scene):
    start, end = scene.frame_start, scene.frame_end
    animated, python_drivers = [], 0
    for obj in scene.objects:
        curves, sources, nla = [], [], []
        for label, block in (
            ("object", obj),
            ("data", obj.data),
            ("shape_keys", getattr(obj.data, "shape_keys", None)),
        ):
            if block is None:
                continue
            found, ranges = fcurves_of(block)
            if found or ranges:
                sources.append(label)
                curves += found
                nla += ranges
            anim = getattr(block, "animation_data", None)
            for driver in anim.drivers if anim is not None else []:
                if driver.driver.type == "SCRIPTED" and not getattr(
                    driver.driver, "is_simple_expression", True
                ):
                    python_drivers += 1
        if not curves and not nla:
            continue
        frames, non_finite, keys = [], 0, 0
        for fcurve in curves:
            for point in fcurve.keyframe_points:
                keys += 1
                if not all(math.isfinite(v) for v in (*point.co, *point.handle_left, *point.handle_right)):
                    non_finite += 1
                if math.isfinite(point.co[0]):
                    frames.append(point.co[0])
        frames += [f for r in nla for f in r]
        animated.append(
            {
                "name": obj.name,
                "sources": sources,
                "channels": sorted({c.data_path for c in curves})[:12],
                "fcurves": len(curves),
                "keyframes": keys,
                "key_range": vec([min(frames), max(frames)], 2) if frames else None,
                "non_finite_keys": non_finite,
                "keys_before_start": sum(f < start for f in frames),
                "keys_after_end": sum(f > end for f in frames),
                "nla_strips": len(nla),
            }
        )
    return {
        "frame_start": start,
        "frame_end": end,
        "frame_current": scene.frame_current,
        "fps": num(scene.render.fps / scene.render.fps_base, 3),
        "objects": animated,
        "python_drivers_not_evaluated": python_drivers,
    }


def motion_facts(scene, tracked, camera_obj, subject_names, samples):
    """World-space motion of objects and whether the subject stays in frame, sampled over the range."""
    start, end = scene.frame_start, scene.frame_end
    count = max(2, min(samples, end - start + 1))
    frames = sorted({int(round(start + i * (end - start) / (count - 1))) for i in range(count)})
    original = scene.frame_current
    centers = {name: [] for name in tracked}
    subject_in_frame, camera_path = [], []
    for frame in frames:
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        camera = None
        if camera_obj is not None and camera_obj.type == "CAMERA" and camera_obj.data.type != "PANO":
            camera = CameraModel(scene, camera_obj)
            camera_path.append(camera.origin.copy())
        subject_points = []
        for name in tracked:
            obj = bpy.data.objects[name].evaluated_get(depsgraph)
            corners = np.array([obj.matrix_world @ Vector(c) for c in obj.bound_box])
            centers[name].append(corners.mean(axis=0))
            if name in subject_names:
                subject_points.append(corners)
        if camera is not None and subject_points:
            x, y, z = camera.project(np.concatenate(subject_points))
            subject_in_frame.append(float(camera.inside(x, y, z).mean()))
    scene.frame_set(original)
    fps = scene.render.fps / scene.render.fps_base
    moving = {}
    for name, path in centers.items():
        path = np.array(path)
        steps = np.linalg.norm(np.diff(path, axis=0), axis=1)
        if steps.sum() <= 1e-6:
            continue
        speeds = steps / np.maximum(np.diff(frames), 1) * fps
        median = float(np.median(speeds[speeds > 0])) if (speeds > 0).any() else 0.0
        moving[name] = {
            "path_length": num(steps.sum()),
            "displacement": num(np.linalg.norm(path[-1] - path[0])),
            "max_speed": num(speeds.max()),
            "start": vec(path[0]),
            "end": vec(path[-1]),
            "jumps": [
                [frames[i], frames[i + 1], num(steps[i])]
                for i in range(len(steps))
                if median > 0 and speeds[i] > 8 * median and steps[i] > 0.05
            ],
        }
    result = {"frames": frames, "objects": moving}
    if camera_path:
        result["camera_path_length"] = num(
            np.linalg.norm(np.diff(np.array(camera_path), axis=0), axis=1).sum()
        )
    if subject_in_frame:
        result["subject_in_frame"] = [num(v, 3) for v in subject_in_frame]
    return result


def missing_images(used_images):
    missing = []
    for image in bpy.data.images:
        if image.source not in {"FILE", "SEQUENCE"} or not image.filepath or image.packed_file:
            continue
        if "<UDIM>" in image.filepath:
            continue  # tiles are separate files; Blender reports missing tiles at render time
        if not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
            missing.append(
                {"name": image.name, "filepath": image.filepath, "used": image.name in used_images}
            )
    return missing


def preview_render(scene, path, percentage, samples):
    """A small final-engine render so exposure can be measured without a vision model.

    A scene that cannot render (no camera, engine error) still gets its inspection: the preview
    records why it was skipped instead of failing the whole run.
    """
    started = time.perf_counter()
    if scene.camera is None:
        return {"file": None, "skipped": "the scene has no active camera"}
    render = scene.render
    render.resolution_percentage = percentage
    if render.engine == "CYCLES":
        scene.cycles.samples = samples
    elif render.engine.startswith("BLENDER_EEVEE"):
        scene.eevee.taa_render_samples = samples
    settings = render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "IMAGE"  # Blender 5.x: must precede the PNG format
    settings.file_format = "PNG"
    settings.color_mode = "RGBA" if render.film_transparent else "RGB"
    settings.color_depth = "8"
    render.filepath = str(path)
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as exc:
        return {"file": None, "skipped": f"render failed: {str(exc).strip()}"}
    return {
        "file": Path(path).name,
        "percentage": percentage,
        "samples": samples,
        "engine": render.engine,
        "seconds": num(time.perf_counter() - started, 2),
    }


def degenerate_axes(matrix):
    axes = [float(np.linalg.norm(matrix[:3, c])) for c in range(3)]
    if not all(math.isfinite(a) for a in axes):
        return axes, math.nan, 3
    det = float(np.linalg.det(matrix[:3, :3]))
    collapsed = sum(a <= 1e-8 * max(1.0, max(axes)) for a in axes)
    if collapsed == 0 and abs(det) <= 1e-9 * axes[0] * axes[1] * axes[2]:
        collapsed = 1  # axes sheared onto a plane
    return axes, det, collapsed


# ---------------------------------------------------------------- main


def inspect(args):
    started = time.perf_counter()
    if args.scene:
        if args.scene not in bpy.data.scenes:
            raise SystemExit(
                f"Scene {args.scene!r} not found; scenes: {', '.join(s.name for s in bpy.data.scenes)}"
            )
        bpy.context.window.scene = bpy.data.scenes[args.scene]
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    unit_scale = scene.unit_settings.scale_length or 1.0
    paths = collection_paths(view_layer)
    vis = {obj.name: visibility(obj, paths, view_layer) for obj in scene.objects}
    mirror_render_visibility(scene, view_layer)
    owners = collect_geometry(bpy.context.evaluated_depsgraph_get())

    camera_obj = scene.camera
    camera = None
    if camera_obj is not None and camera_obj.type == "CAMERA" and camera_obj.data.type != "PANO":
        camera = CameraModel(scene, camera_obj)

    names = sorted(owners)
    boxes = [owners[n] for n in names if np.all(np.isfinite(owners[n]["min"]))]
    scale = 1.0
    if boxes:
        extent = np.max([o["max"] for o in boxes], axis=0) - np.min([o["min"] for o in boxes], axis=0)
        scale = max(float(np.linalg.norm(extent)), 1e-6)
    material_info = {}
    for name in names:
        for mat_name in owners[name]["materials"]:
            if mat_name not in material_info and mat_name in bpy.data.materials:
                material_info[mat_name] = material_facts(bpy.data.materials[mat_name])
    see_through_materials = {m for m, info in material_info.items() if info["see_through"]}

    for name in names:
        verts, tris = owner_arrays(owners[name])
        seed = int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16)
        points, normals, area = surface_samples(verts, tris, args.samples, seed)
        owners[name].update(samples=points, normals=normals, area=area, verts=verts)

    rays = SceneRays(owners, names, scale)
    index = {n: i for i, n in enumerate(names)}
    camera_hidden = {n for n in names if n in vis and vis[n][1]}
    hidden_from_camera = frozenset(index[n] for n in camera_hidden)
    shadow_skip = frozenset(
        index[n]
        for n in names
        if (owners[n]["materials"] and owners[n]["materials"] <= see_through_materials)
        or (n in bpy.data.objects and not getattr(bpy.data.objects[n], "visible_shadow", True))
    )
    solid = [n for n in names if owners[n]["area"] > 0 and owners[n]["finite"]]
    candidates = [n for n in solid if n not in camera_hidden]
    subject, environment, method = choose_subject(
        owners, candidates, args.subject, args.subject_collection, camera
    )

    views, seen_masks, flipped_normals, grid_info = {}, {}, {}, None
    if camera is not None:
        for name in names:
            if name in camera_hidden:
                continue
            rec = owners[name]
            view, seen, flipped = camera_view(
                camera, rays, index[name], rec["samples"], rec["normals"], rec["verts"], hidden_from_camera
            )
            view["coverage"] = 0.0
            views[name], seen_masks[name], flipped_normals[name] = view, seen, flipped
        if rays.tree is not None:
            render = scene.render
            aspect = (render.resolution_x * render.pixel_aspect_x) / max(
                1, render.resolution_y * render.pixel_aspect_y
            )
            grid, counts, backfaces, rows = coverage_grid(camera, rays, hidden_from_camera, args.grid, aspect)
            total = args.grid * rows
            for owner, count in counts.items():
                views[names[owner]]["coverage"] = num(count / total)
            legend, encoded = encode_grid(grid, counts, names)
            inside = None
            center_owner = grid[rows // 2][args.grid // 2]
            if center_owner >= 0 and backfaces[center_owner] > 0.5 * counts[center_owner]:
                back = rays.first(camera.origin, -camera.forward, 1e9, hidden_from_camera)
                if back is not None and back[0] == center_owner and back[2].dot(Vector(-camera.forward)) > 0:
                    inside = names[center_owner]
            grid_info = {
                "size": [args.grid, rows],
                "background": num(1 - sum(counts.values()) / total),
                "legend": legend,
                "rows": encoded,
                "camera_inside": inside,
            }

    subject_info = None
    basis = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0))
    if subject:
        lo = np.min([owners[n]["min"] for n in subject], axis=0)
        hi = np.max([owners[n]["max"] for n in subject], axis=0)
        center = (lo + hi) / 2
        subject_info = {
            "method": method,
            "objects": subject,
            "environment": environment,
            "bbox_min": vec(lo),
            "bbox_max": vec(hi),
            "center": vec(center),
            "radius": num(np.linalg.norm(hi - lo) / 2),
        }
        pts, nrm, wts = [], [], []
        if camera is not None:
            area = {n: owners[n]["area"] for n in subject}
            total_area = sum(area.values()) or 1.0
            framed = {n: area[n] * (views[n]["in_frame"] or 0.0) for n in subject}
            subject_info["in_frame"] = num(sum(framed.values()) / total_area)
            subject_info["occluded"] = num(
                sum(framed[n] * (views[n].get("occluded") or 0.0) for n in subject)
                / (sum(framed.values()) or 1.0)
            )
            subject_info["coverage"] = num(sum(views[n]["coverage"] for n in subject))
            boxes = [views[n]["screen_bbox"] for n in subject if "screen_bbox" in views[n]]
            edges = {e for n in subject for e in views[n].get("cut_off", [])}
            if boxes:
                box = [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
                subject_info["screen_bbox"] = vec(box, 3)
                if subject_info["in_frame"]:
                    # Parts of the subject can be wholly outside the frame (e.g. lifted above it).
                    for edge, beyond in zip(
                        ("left", "bottom", "right", "top"),
                        (box[0] < -0.001, box[1] < -0.001, box[2] > 1.001, box[3] > 1.001),
                    ):
                        if beyond:
                            edges.add(edge)
            subject_info["cut_off"] = sorted(edges)
            cx, cy, cz = camera.project(center[None, :])
            subject_info["center_screen"] = vec([cx[0], cy[0]], 3) if cz[0] > 0 else None
            subject_info["distance"] = num(np.linalg.norm(center - camera.origin))
            for n in subject:
                mask = seen_masks[n]
                if mask.any():
                    pts.append(owners[n]["samples"][mask])
                    nrm.append(flipped_normals[n][mask])
                    wts.append(np.full(int(mask.sum()), area[n] / len(owners[n]["samples"])))
        subject_info["light_basis"] = "camera-visible subject surface"
        if not pts:
            subject_info["light_basis"] = "whole subject surface (the camera sees none of it)"
            for n in subject:
                pts.append(owners[n]["samples"])
                nrm.append(owners[n]["normals"])
                wts.append(np.full(len(owners[n]["samples"]), owners[n]["area"] / len(owners[n]["samples"])))
        p, n_, w = np.concatenate(pts), np.concatenate(nrm), np.concatenate(wts)
        if len(p) > 1024:
            keep = np.linspace(0, len(p) - 1, 1024).astype(int)
            p, n_, w = p[keep], n_[keep], w[keep]
        basis = (p, n_, w)

    tolerance = CONTACT_TOLERANCE_M / unit_scale * args.contact_scale
    support, floating = (
        contact_analysis(owners, solid, rays, tolerance) if rays.tree is not None else ({}, [])
    )

    light_objects = [(o, vis[o.name][0]) for o in scene.objects if o.type == "LIGHT"]
    lights = light_analysis(
        light_objects,
        basis,
        rays,
        shadow_skip,
        np.array(subject_info["center"]) if subject_info else None,
        camera,
    )

    used_images = {img for info in material_info.values() for img in info["images"]}
    if scene.world is not None and uses_nodes(scene.world):
        used_images |= {
            n.image.name
            for n in reachable_nodes(scene.world.node_tree)
            if n.type == "TEX_ENVIRONMENT" and n.image
        }
    material_users = {}
    for name in names:
        for mat_name in owners[name]["materials"]:
            material_users.setdefault(mat_name, []).append(name)
    materials = [
        {**material_info[m], "users": sorted(material_users.get(m, []))} for m in sorted(material_info)
    ]
    unused_emissive = sorted(
        m.name for m in bpy.data.materials if m.name not in material_info and material_facts(m)["emission"]
    )

    objects, hashes = [], {}
    for obj in scene.objects:
        reasons, camera_reasons = vis[obj.name]
        matrix = np.array(obj.matrix_world, dtype=np.float64)
        axes, det, collapsed = degenerate_axes(matrix)
        record = {
            "name": obj.name,
            "type": obj.type,
            "data": obj.data.name if obj.data is not None else None,
            "parent": obj.parent.name if obj.parent else None,
            "collections": sorted(c.name for c in obj.users_collection),
            "hide_render": bool(obj.hide_render),
            "render_visible": not reasons,
            "camera_visible": not reasons and not camera_reasons,
            "hidden_by": reasons + camera_reasons,
            "location": vec(matrix[:3, 3]),
            "rotation_euler": vec(obj.rotation_euler),
            "scale": vec(obj.scale),
            "matrix_world": [vec(row, 5) for row in matrix],
            "finite": bool(np.isfinite(matrix).all()),
            "world_determinant": num(det, 9),
            "world_axis_lengths": vec(axes, 6),
            "degenerate_axes": collapsed,
            "material_count": 0,
            "vertices": 0,
            "polygons": 0,
        }
        if obj.type == "MESH":
            record["mesh_hash"] = mesh_hash(obj.data, hashes)
        if obj.modifiers:
            record["modifiers"] = [m.type for m in obj.modifiers]
        rec = owners.get(obj.name)
        if rec is not None:
            record.update(
                renders_geometry=rec["polygons"] > 0,
                vertices=rec["vertices"],
                polygons=rec["polygons"],
                triangles=rec["triangles"],
                instances=rec["instances"],
                materials=sorted(rec["materials"]),
                material_count=len(rec["materials"]),
                faces_without_material=rec["unassigned"],
                finite=record["finite"] and rec["finite"],
                area=num(rec["area"], 5),
                role="subject"
                if obj.name in subject
                else ("environment" if obj.name in environment else None),
            )
            if np.all(np.isfinite(rec["min"])):
                record.update(
                    bbox_min=vec(rec["min"]),
                    bbox_max=vec(rec["max"]),
                    dimensions=vec(rec["max"] - rec["min"]),
                )
            if rec["truncated"]:
                record["raycast_truncated"] = True
            if obj.name in views:
                record["view"] = views[obj.name]
            if obj.name in support:
                record["support"] = support[obj.name]
        elif obj.type in GEOMETRY_TYPES:
            record["renders_geometry"] = False
        objects.append(record)

    animation = animation_facts(scene)
    if animation["objects"] and args.animation_samples > 1:
        tracked = [n for n in names if n in bpy.data.objects and not owners[n]["truncated"]]
        animation["motion"] = motion_facts(scene, tracked, camera_obj, set(subject), args.animation_samples)

    file_facts = None
    if bpy.data.filepath:
        blend = Path(bpy.data.filepath)
        digest = hashlib.sha256()
        with open(blend, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        file_facts = {"name": blend.name, "sha256": digest.hexdigest(), "bytes": blend.stat().st_size}

    render = scene.render
    if render.engine == "CYCLES":
        samples = scene.cycles.samples
    elif render.engine.startswith("BLENDER_EEVEE"):
        samples = scene.eevee.taa_render_samples
    else:
        samples = None
    camera_facts = camera.facts() if camera is not None else None
    if camera is None and camera_obj is not None and camera_obj.type == "CAMERA":
        matrix = camera_obj.matrix_world.normalized()
        camera_facts = {
            "name": camera_obj.name,
            "type": "PANO",
            "location": vec(matrix.translation),
            "rotation_euler": vec(camera_obj.rotation_euler),
            "forward": vec(-np.array(matrix.to_3x3().col[2])),
            "note": "panoramic camera: framing not analysed",
        }
    report = {
        "schema_version": SCHEMA_VERSION,
        "blender_version": bpy.app.version_string,
        "file": file_facts,
        "scene": scene.name,
        "scenes": [{"name": s.name, "objects": len(s.objects)} for s in bpy.data.scenes],
        "view_layer": view_layer.name,
        "engine": render.engine,
        "resolution": [
            round(render.resolution_x * render.resolution_percentage / 100),
            round(render.resolution_y * render.resolution_percentage / 100),
        ],
        "render": {
            "samples": samples,
            "film_transparent": bool(render.film_transparent),
            "view_transform": scene.view_settings.view_transform,
            "look": scene.view_settings.look,
            "exposure": num(scene.view_settings.exposure),
            "gamma": num(scene.view_settings.gamma),
        },
        "units": {"system": scene.unit_settings.system, "scale_length": num(unit_scale, 6)},
        "camera": camera_facts,
        "frame": grid_info,
        "subject": subject_info,
        "objects": objects,
        "lights": lights,
        "world": world_facts(scene),
        "materials": materials,
        "illumination": {
            "lights": len(light_objects),
            "render_visible_lights": sum(1 for f in lights if f["render_visible"] and (f["energy"] or 0) > 0),
            "lights_reaching_subject": sum(1 for f in lights if (f.get("reaches_subject") or 0) > 0.01),
            "emissive_materials": [m["name"] for m in materials if m["emission"]],
            "unused_emissive_materials": unused_emissive,
        },
        "contacts": {"tolerance": num(tolerance, 6), "floating": floating},
        "animation": animation,
        "missing_images": missing_images(used_images),
        "inspector": {
            "samples_per_object": args.samples,
            "raycast": rays.tree is not None,
            "raycast_truncated": any(o["truncated"] for o in owners.values()),
            "seconds": num(time.perf_counter() - started, 2),
        },
    }
    if args.preview:
        report["preview"] = preview_render(
            scene, Path(args.preview), args.preview_percentage, args.preview_samples
        )
    return clean(report)


NUMBER = r"(?:-?\d[\d.eE+-]*|null)"


def compact_json(data):
    """Indented JSON with numeric arrays kept on one line."""
    text = json.dumps(data, indent=2, allow_nan=False)
    return re.sub(
        rf"\[\s+({NUMBER}(?:,\s+{NUMBER})*)\s+\]",
        lambda m: "[" + ", ".join(part.strip() for part in m.group(1).split(",")) + "]",
        text,
    )


def parse(argv):
    parser = argparse.ArgumentParser(prog="inspect_scene.py")
    parser.add_argument("--output", required=True)
    parser.add_argument("--scene", help="inspect this scene instead of the active one")
    parser.add_argument(
        "--subject", action="append", default=[], help="subject object name or glob (repeatable)"
    )
    parser.add_argument(
        "--subject-collection", action="append", default=[], help="collection holding the subject"
    )
    parser.add_argument("--grid", type=int, default=GRID_COLUMNS, help="columns of the camera coverage grid")
    parser.add_argument("--samples", type=int, default=SAMPLES, help="surface samples per object")
    parser.add_argument(
        "--contact-scale", type=float, default=1.0, help="multiplier for the 5 mm contact tolerance"
    )
    parser.add_argument("--animation-samples", type=int, default=ANIMATION_SAMPLES)
    parser.add_argument("--preview", help="also render a small preview PNG to this path")
    parser.add_argument("--preview-percentage", type=int, default=25)
    parser.add_argument("--preview-samples", type=int, default=16)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    target = Path(arguments.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(compact_json(inspect(arguments)), encoding="utf-8")
    print("QUALITY_LAB_INSPECTION=" + str(target))
