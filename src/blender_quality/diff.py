"""Objective before/after comparison of two schema v2 inspections.

It answers what an edit changed (objects added, removed, renamed, moved, re-meshed, re-materialed;
camera, lights, world and render settings) and checks the preserve-and-relight brief: geometry,
names and materials untouched, lighting or camera changed, input file not overwritten.
"""

import hashlib
import math
from pathlib import Path

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}
TOLERANCE = 1e-4
MATERIAL_FACTS = (
    "base_color",
    "metallic",
    "roughness",
    "transmission",
    "alpha",
    "emission",
    "shaders",
    "images",
)


def _require_v2(scene, label):
    if not isinstance(scene, dict) or scene.get("schema_version") != 2:
        raise ValueError(f"{label} must be a schema_version 2 inspection; re-run `blender-quality inspect`")


def _is_geometry(obj):
    return obj["type"] in GEOMETRY_TYPES or bool(obj.get("renders_geometry"))


def _signature(obj):
    return (
        obj["type"],
        obj.get("mesh_hash"),
        obj.get("vertices"),
        obj.get("polygons"),
        tuple(obj.get("materials", [])),
    )


def _max_difference(a, b):
    if a is None or b is None:
        return math.inf if a != b else 0.0
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b)
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return max((_max_difference(x, y) for x, y in zip(a, b)), default=0.0)
    return 0.0 if a == b else math.inf


def _fmt(values):
    return "(" + ", ".join(f"{v:g}" for v in values) + ")"


def object_changes(old, new):
    changes = []
    old_m, new_m = old.get("matrix_world"), new.get("matrix_world")
    if old_m and new_m:
        moved = [new_m[i][3] - old_m[i][3] for i in range(3)]
        if max(abs(v) for v in moved) > TOLERANCE:
            changes.append(f"moved by {_fmt(round(v, 4) for v in moved)}")
        basis = max(abs(new_m[r][c] - old_m[r][c]) for r in range(3) for c in range(3))
        if basis > TOLERANCE:
            axes_old, axes_new = old.get("world_axis_lengths"), new.get("world_axis_lengths")
            if axes_old and axes_new and _max_difference(axes_old, axes_new) > TOLERANCE:
                changes.append(f"world scale {_fmt(axes_old)} -> {_fmt(axes_new)}")
            else:
                changes.append("rotated")
    if old.get("mesh_hash") != new.get("mesh_hash"):
        changes.append("mesh data edited")
    for key in ("vertices", "polygons"):
        if old.get(key) != new.get(key):
            changes.append(f"{key} {old.get(key)} -> {new.get(key)}")
    if old.get("materials", []) != new.get("materials", []):
        changes.append(f"materials {old.get('materials', [])} -> {new.get('materials', [])}")
    if old.get("modifiers", []) != new.get("modifiers", []):
        changes.append(f"modifiers {old.get('modifiers', [])} -> {new.get('modifiers', [])}")
    if old.get("parent") != new.get("parent"):
        changes.append(f"parent {old.get('parent')!r} -> {new.get('parent')!r}")
    if old.get("render_visible") != new.get("render_visible"):
        changes.append("now hidden from render" if old.get("render_visible") else "now renders")
    return changes


def _named(items):
    return {item["name"]: item for item in items}


def camera_changes(old, new):
    if old is None or new is None:
        return [] if old == new else [f"camera {old and old['name']!r} -> {new and new['name']!r}"]
    changes = []
    if old["name"] != new["name"]:
        changes.append(f"active camera '{old['name']}' -> '{new['name']}'")
    if _max_difference(old.get("location"), new.get("location")) > TOLERANCE:
        changes.append(f"moved {_fmt(old['location'])} -> {_fmt(new['location'])}")
    if _max_difference(old.get("forward"), new.get("forward")) > TOLERANCE:
        changes.append(f"re-aimed {_fmt(old['forward'])} -> {_fmt(new['forward'])}")
    for key in ("lens_mm", "ortho_scale", "type"):
        if old.get(key) != new.get(key):
            changes.append(f"{key} {old.get(key)} -> {new.get(key)}")
    if old.get("dof") != new.get("dof"):
        changes.append("depth of field changed")
    return changes


def light_changes(old, new):
    changes = []
    for key in (
        "type",
        "energy",
        "exposure",
        "color",
        "size",
        "spot_size_deg",
        "spread_deg",
        "shape",
        "render_visible",
    ):
        if _max_difference(old.get(key), new.get(key)) > TOLERANCE:
            changes.append(f"{key} {old.get(key)} -> {new.get(key)}")
    if _max_difference(old.get("location"), new.get("location")) > TOLERANCE:
        changes.append(f"moved {_fmt(old['location'])} -> {_fmt(new['location'])}")
    if _max_difference(old.get("direction"), new.get("direction")) > TOLERANCE:
        changes.append("re-aimed")
    return changes


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diff_inspections(before, after, original=None):
    _require_v2(before, "BEFORE")
    _require_v2(after, "AFTER")
    old_objects, new_objects = _named(before["objects"]), _named(after["objects"])
    added = sorted(set(new_objects) - set(old_objects))
    removed = sorted(set(old_objects) - set(new_objects))
    renamed = []
    for old_name in list(removed):
        matches = [n for n in added if _signature(new_objects[n]) == _signature(old_objects[old_name])]
        if len(matches) == 1 and old_objects[old_name].get("mesh_hash") is not None:
            renamed.append([old_name, matches[0]])
            removed.remove(old_name)
            added.remove(matches[0])
    changed = []
    for old_name, new_name in [(n, n) for n in sorted(set(old_objects) & set(new_objects))] + [
        tuple(p) for p in renamed
    ]:
        if new_objects[new_name]["type"] in {"LIGHT", "CAMERA"}:
            continue  # reported in the lights and camera sections
        found = object_changes(old_objects[old_name], new_objects[new_name])
        if found:
            changed.append({"name": new_name, "type": new_objects[new_name]["type"], "changes": found})

    old_lights, new_lights = _named(before["lights"]), _named(after["lights"])
    lights = {
        "added": sorted(set(new_lights) - set(old_lights)),
        "removed": sorted(set(old_lights) - set(new_lights)),
        "changed": [
            {"name": n, "changes": c}
            for n in sorted(set(old_lights) & set(new_lights))
            if (c := light_changes(old_lights[n], new_lights[n]))
        ],
    }
    world = [
        f"{key} {before['world'].get(key)} -> {after['world'].get(key)}"
        for key in ("name", "strength", "color", "textured")
        if _max_difference(before["world"].get(key), after["world"].get(key)) > TOLERANCE
    ]
    old_materials, new_materials = _named(before["materials"]), _named(after["materials"])
    materials = {
        "added": sorted(set(new_materials) - set(old_materials)),
        "removed": sorted(set(old_materials) - set(new_materials)),
        "changed": sorted(
            n
            for n in set(old_materials) & set(new_materials)
            if any(old_materials[n].get(k) != new_materials[n].get(k) for k in MATERIAL_FACTS)
        ),
    }
    render = [
        f"{key} {before.get(key)} -> {after.get(key)}"
        for key in ("engine", "resolution")
        if before.get(key) != after.get(key)
    ]
    render += [
        f"{key} {before['render'].get(key)} -> {after['render'].get(key)}"
        for key in ("view_transform", "look", "exposure", "film_transparent", "samples")
        if before.get("render", {}).get(key) != after.get("render", {}).get(key)
    ]
    camera = camera_changes(before["camera"], after["camera"])

    geometry_changed = [c["name"] for c in changed if _is_geometry(new_objects[c["name"]])]
    geometry_added = [n for n in added if _is_geometry(new_objects[n])]
    geometry_removed = [n for n in removed if _is_geometry(old_objects[n])]
    input_unchanged = None
    if original is not None:
        recorded = (before.get("file") or {}).get("sha256")
        if not recorded:
            raise ValueError(
                "BEFORE has no recorded file hash; inspect the original .blend with this version"
            )
        input_unchanged = sha256_file(original) == recorded
    verdict = {
        "geometry_preserved": not (geometry_changed or geometry_added or geometry_removed or renamed),
        "names_preserved": not removed and not renamed,
        "materials_preserved": not materials["removed"] and not materials["changed"],
        "lighting_changed": bool(lights["added"] or lights["removed"] or lights["changed"] or world),
        "camera_changed": bool(camera),
        "input_unchanged": input_unchanged,
    }
    verdict["passed"] = (
        verdict["geometry_preserved"]
        and verdict["names_preserved"]
        and verdict["materials_preserved"]
        and (verdict["lighting_changed"] or verdict["camera_changed"])
        and input_unchanged is not False
    )
    framing = {}
    for label, scene in (("before", before), ("after", after)):
        subject = scene.get("subject") or {}
        framing[label] = {k: subject.get(k) for k in ("coverage", "in_frame", "occluded", "center_screen")}
    result = {
        "kind": "scene_diff",
        "before": {"file": (before.get("file") or {}).get("name"), "scene": before.get("scene")},
        "after": {"file": (after.get("file") or {}).get("name"), "scene": after.get("scene")},
        "objects": {"added": added, "removed": removed, "renamed": renamed, "changed": changed},
        "camera": camera,
        "lights": lights,
        "world": world,
        "materials": materials,
        "render": render,
        "framing": framing,
        "preserve_and_relight": verdict,
    }
    result["summary"] = summary_lines(result)
    return result


def summary_lines(diff):
    lines = []
    objects = diff["objects"]
    for key, label in (("added", "Added"), ("removed", "Removed")):
        if objects[key]:
            lines.append(f"{label} objects: {', '.join(objects[key])}")
    for old, new in objects["renamed"]:
        lines.append(f"Renamed '{old}' -> '{new}'")
    for item in objects["changed"]:
        lines.append(f"'{item['name']}': {'; '.join(item['changes'])}")
    if diff["camera"]:
        lines.append(f"Camera: {'; '.join(diff['camera'])}")
    lights = diff["lights"]
    if lights["added"]:
        lines.append(f"Added lights: {', '.join(lights['added'])}")
    if lights["removed"]:
        lines.append(f"Removed lights: {', '.join(lights['removed'])}")
    for item in lights["changed"]:
        lines.append(f"Light '{item['name']}': {'; '.join(item['changes'])}")
    if diff["world"]:
        lines.append(f"World: {'; '.join(diff['world'])}")
    materials = diff["materials"]
    for key in ("added", "removed", "changed"):
        if materials[key]:
            lines.append(f"Materials {key}: {', '.join(materials[key])}")
    if diff["render"]:
        lines.append(f"Render: {'; '.join(diff['render'])}")
    return lines or ["No changes"]


def to_markdown(diff):
    verdict = diff["preserve_and_relight"]
    lines = [f"# Scene diff: {diff['before']['file']} -> {diff['after']['file']}", "", "## Changes", ""]
    lines += [f"- {line}" for line in diff["summary"]]
    lines += ["", "## Preserve-and-relight check", ""]
    for key in (
        "geometry_preserved",
        "names_preserved",
        "materials_preserved",
        "lighting_changed",
        "camera_changed",
        "input_unchanged",
    ):
        value = verdict[key]
        lines.append(
            f"- {key.replace('_', ' ')}: {'not checked (pass --original)' if value is None else ('yes' if value else 'NO')}"
        )
    lines.append(f"\n**{'PASS' if verdict['passed'] else 'FAIL'}**")
    framing = diff["framing"]
    if framing["before"].get("coverage") is not None and framing["after"].get("coverage") is not None:
        lines.append(
            f"\nSubject frame share {framing['before']['coverage']} -> {framing['after']['coverage']}, "
            f"hidden {framing['before']['occluded']} -> {framing['after']['occluded']}."
        )
    return "\n".join(lines) + "\n"


def original_path(value):
    path = Path(value)
    if not path.is_file():
        raise ValueError(f"--original {value}: file not found")
    return path
