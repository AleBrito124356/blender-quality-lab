"""Technical gates and advisory warnings for inspection schema v2.

Gates are hard, objective checks: `score --strict` fails when any gate fails. A gate that cannot be
judged because a more basic gate failed (no camera, nothing renders, collapsed transforms) is
reported as failed with `blocked_by`, so one broken thing shows up as one primary failure.
Warnings are advisory: they point at likely problems that can also be intentional.
"""

import math

TINY_SUBJECT = 0.005  # share of the frame; below this the subject is a speck
SMALL_SUBJECT = 0.05
MIN_IN_FRAME = 0.35  # share of the subject's surface that must lie inside the frame
MIN_VISIBLE_IN_FRAME = 0.05
HIDDEN = 0.95  # share of in-frame subject surface hidden behind other objects
FLAT_RATIO = 1.25
HARSH_RATIO = 8.0

V2_FIELDS = {
    "objects": list,
    "camera": (dict, type(None)),
    "subject": (dict, type(None)),
    "lights": list,
    "world": dict,
    "illumination": dict,
    "contacts": dict,
    "animation": dict,
    "missing_images": list,
    "resolution": list,
}
V2_OBJECT_FIELDS = (
    "name",
    "type",
    "render_visible",
    "camera_visible",
    "hidden_by",
    "finite",
    "degenerate_axes",
)
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}


def validate(scene):
    for key, kind in V2_FIELDS.items():
        if key not in scene:
            raise ValueError(f"inspection is missing the required field '{key}'")
        if not isinstance(scene[key], kind):
            raise ValueError(f"inspection field '{key}' has the wrong type ({type(scene[key]).__name__})")
    if len(scene["resolution"]) != 2:
        raise ValueError("inspection field 'resolution' must be [width, height]")
    for index, obj in enumerate(scene["objects"]):
        if not isinstance(obj, dict):
            raise ValueError(f"inspection objects[{index}] is not an object")
        for key in V2_OBJECT_FIELDS:
            if key not in obj:
                raise ValueError(f"inspection objects[{index}] is missing '{key}'")


def pct(value):
    return f"{100 * value:.1f}%"


def names(items, limit=4):
    items = list(items)
    shown = ", ".join(f"'{n}'" for n in items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def geometry(scene):
    """Objects that produce render geometry (from the depsgraph, after instancing and modifiers)."""
    return [o for o in scene["objects"] if o.get("renders_geometry")]


def lighting_summary(scene):
    """Lights ranked by estimated irradiance on the camera-visible subject, plus key:fill ratio."""
    lights = [light for light in scene["lights"] if (light.get("irradiance") or 0) > 0]
    ranked = sorted(lights, key=lambda light: -light["irradiance"])
    world = scene["world"]
    ambient = math.pi * (world.get("radiance") or 0.0)
    summary = {"ranked": [(light["name"], light["irradiance"]) for light in ranked], "ambient": ambient}
    if ranked:
        key = ranked[0]
        summary["key"] = key["name"]
        if len(ranked) > 1:
            summary["fill"] = ranked[1]["name"]
            summary["key_to_fill"] = key["irradiance"] / ranked[1]["irradiance"]
        elif ambient > 0:
            summary["key_to_fill"] = key["irradiance"] / ambient if ambient else None
    return summary


def illumination_sources(scene):
    """(sources that light the subject, explanation) - used by the effective_illumination gate."""
    sources = []
    for light in scene["lights"]:
        if not light.get("render_visible") or (light.get("energy") or 0) <= 0:
            continue
        if max(light.get("color") or [0]) <= 0:
            continue
        reach = light.get("reaches_subject")
        if (reach is not None and reach > 0.005) or (
            reach is None and light.get("aimed_at_subject") is not False
        ):
            sources.append(f"light '{light['name']}'")
    world = scene["world"]
    if (world.get("radiance") or 0) > 0 or (world.get("textured") and (world.get("strength") or 0) > 0):
        sources.append(f"world '{world.get('name')}'")
    for material in scene["illumination"].get("emissive_materials", []):
        sources.append(f"emissive material '{material}'")
    return sources


def _hidden_geometry_detail(scene):
    reasons = {}
    for obj in scene["objects"]:
        if obj["type"] in GEOMETRY_TYPES and obj["hidden_by"]:
            reasons.setdefault(obj["hidden_by"][0], []).append(obj["name"])
    if not reasons:
        return "the scene has no geometry that renders"
    return "; ".join(f"{names(objs)}: {reason}" for reason, objs in reasons.items())


def gates(scene, strict_contact=False):
    objects = geometry(scene)
    camera = scene["camera"]
    subject = scene["subject"]
    frame = scene.get("frame")
    checks = []

    def add(key, passed, description, detail="", blocked_by=None):
        entry = {"id": key, "passed": bool(passed), "description": description, "detail": detail}
        if blocked_by:
            entry["blocked_by"] = blocked_by
            entry["passed"] = False
        checks.append(entry)
        return entry["passed"]

    visible = [o for o in objects if o["camera_visible"] and o.get("polygons", 0) > 0]
    has_geometry = add(
        "renderable_geometry",
        visible,
        "Something the camera can see renders geometry (object, collection, view-layer and instancer visibility)",
        f"{len(visible)} visible objects render geometry" if visible else _hidden_geometry_detail(scene),
    )
    has_camera = add(
        "camera",
        camera is not None,
        "An active render camera exists",
        f"'{camera['name']}'" if camera else "scene.camera is not set",
    )
    broken = [o for o in objects if not o["finite"] or o["degenerate_axes"] >= 2]
    sane = add(
        "non_degenerate_world_transform",
        not broken,
        "Render geometry has finite, non-collapsed world transforms (parents included)",
        (
            f"{names(o['name'] for o in broken)} collapse to a point or line in world space"
            + (f" (parent '{broken[0]['parent']}')" if broken and broken[0].get("parent") else "")
        )
        if broken
        else "",
    )
    prerequisites = [k for k, ok in (("camera", has_camera), ("renderable_geometry", has_geometry)) if not ok]
    if not sane:
        prerequisites.append("non_degenerate_world_transform")
    in_frame_ok = False
    if prerequisites:
        add("subject_in_frame", False, SUBJECT_IN_FRAME, "", blocked_by=prerequisites)
    elif subject is None or subject.get("in_frame") is None:
        add("subject_in_frame", False, SUBJECT_IN_FRAME, "no subject geometry with surface area to frame")
    else:
        share, occluded = subject["in_frame"], subject.get("occluded") or 0.0
        in_frame_ok = share >= MIN_VISIBLE_IN_FRAME and occluded < HIDDEN
        if share < MIN_VISIBLE_IN_FRAME:
            detail = f"only {pct(share)} of the subject surface is inside the frame"
            if subject.get("center_screen") is None:
                detail += " (the subject is behind the camera)"
        elif occluded >= HIDDEN:
            blockers = {
                b
                for o in scene["objects"]
                if o["name"] in subject["objects"]
                for b in o.get("view", {}).get("occluded_by", [])
            }
            detail = f"{pct(occluded)} of the in-frame subject is hidden behind {names(sorted(blockers))}"
        else:
            detail = f"{pct(share)} of the subject surface is in frame, {pct(occluded)} of that hidden"
        add("subject_in_frame", in_frame_ok, SUBJECT_IN_FRAME, detail)
    if not in_frame_ok:
        add("not_cropped_or_tiny", False, NOT_CROPPED, "", blocked_by=prerequisites or ["subject_in_frame"])
    else:
        coverage = subject.get("coverage")
        problems = []
        if frame is not None and coverage is not None and coverage < TINY_SUBJECT:
            problems.append(f"the subject fills only {pct(coverage)} of the frame")
        if subject["in_frame"] < MIN_IN_FRAME:
            problems.append(f"only {pct(subject['in_frame'])} of the subject is inside the frame")
        detail = "; ".join(problems) or f"fills {pct(coverage or 0)} of the frame"
        add("not_cropped_or_tiny", not problems, NOT_CROPPED, detail)
    sources = illumination_sources(scene)
    add(
        "effective_illumination",
        sources,
        "A light that reaches the subject, a non-black world or an emissive material on visible geometry",
        ", ".join(sources) if sources else _no_light_detail(scene),
    )
    unmaterialed = [o["name"] for o in visible if o.get("material_count", 0) == 0]
    if not has_geometry:
        add("materials", False, MATERIALS, "", blocked_by=["renderable_geometry"])
    else:
        add(
            "materials",
            not unmaterialed,
            MATERIALS,
            f"no material: {names(unmaterialed)}" if unmaterialed else "",
        )
    used_missing = [m["name"] for m in scene["missing_images"] if m.get("used")]
    add(
        "missing_images",
        not used_missing,
        "No image used by a visible material or the world is missing on disk",
        f"missing: {names(used_missing)}" if used_missing else "",
    )
    width, height = scene["resolution"]
    add(
        "resolution",
        width >= 256 and height >= 256,
        "Effective render resolution is at least 256 x 256",
        f"{width} x {height}",
    )
    add("animation_keys_in_range", *_animation_check(scene["animation"]))
    if strict_contact:
        floating = scene["contacts"].get("floating", [])
        add(
            "grounded",
            not floating,
            "No group of objects floats above the surface below it (--strict-contact)",
            "; ".join(f"{names(g['objects'])} float {g['gap']} above '{g['above']}'" for g in floating),
        )
    return checks


SUBJECT_IN_FRAME = "The subject is inside the camera frame and not hidden behind other objects"
NOT_CROPPED = "The subject fills at least 0.5% of the frame and at least 35% of it lies inside the frame"
MATERIALS = "Every visible object that renders geometry has a material"


def _no_light_detail(scene):
    parts = []
    lights = scene["lights"]
    if not lights:
        parts.append("no lights")
    for light in lights:
        if not light.get("render_visible"):
            parts.append(f"light '{light['name']}' does not render ({'; '.join(light.get('hidden_by', []))})")
        elif (light.get("energy") or 0) <= 0:
            parts.append(f"light '{light['name']}' has zero power")
        elif light.get("aimed_at_subject") is False:
            parts.append(f"light '{light['name']}' points away from the subject")
        elif light.get("reaches_subject") == 0:
            parts.append(f"light '{light['name']}' is blocked by {names(light.get('blocked_by', []))}")
    world = scene["world"]
    parts.append(f"world strength {world.get('strength')}" if world.get("name") else "no world")
    unused = scene["illumination"].get("unused_emissive_materials", [])
    if unused:
        parts.append(f"emissive materials not on any visible object: {names(unused)}")
    return "; ".join(parts)


def _animation_check(animation):
    description = "Animation keys are finite and fall inside the scene frame range"
    animated = animation.get("objects", [])
    if not animated:
        return True, description, "no animation"
    start, end = animation["frame_start"], animation["frame_end"]
    problems = []
    for obj in animated:
        if obj.get("non_finite_keys"):
            problems.append(f"'{obj['name']}' has {obj['non_finite_keys']} non-finite keys")
        key_range = obj.get("key_range")
        if key_range and (key_range[1] < start or key_range[0] > end):
            problems.append(
                f"'{obj['name']}' is keyed on frames {key_range[0]:g}-{key_range[1]:g}, outside {start}-{end}"
            )
    detail = "; ".join(problems) or f"{len(animated)} animated objects within frames {start}-{end}"
    return not problems, description, detail


def warnings(scene):
    found = []

    def warn(key, message, objects=(), severity="warning"):
        found.append({"id": key, "severity": severity, "message": message, "objects": list(objects)})

    subject = scene["subject"] or {}
    for group in scene["contacts"].get("floating", []):
        warn(
            "floating",
            f"{names(group['objects'])} float {group['gap']} scene units above '{group['above']}' and touch nothing "
            "that reaches the ground",
            group["objects"],
        )
    coverage = subject.get("coverage")
    if coverage is not None and TINY_SUBJECT <= coverage < SMALL_SUBJECT and scene.get("frame"):
        warn(
            "small_subject",
            f"The subject fills only {pct(coverage)} of the frame; move the camera closer or use a longer lens",
        )
    if subject.get("in_frame") and subject.get("cut_off"):
        warn(
            "subject_cut_off",
            f"The subject is cut off at the {', '.join(subject['cut_off'])} edge of the frame",
        )
    occluded = subject.get("occluded") or 0.0
    if 0.5 <= occluded < HIDDEN:
        warn(
            "subject_partly_hidden", f"{pct(occluded)} of the in-frame subject is hidden behind other objects"
        )
    for obj in scene["objects"]:
        view = obj.get("view") or {}
        if (
            obj.get("role") == "subject"
            and (view.get("occluded") or 0) >= HIDDEN
            and (view.get("in_frame") or 0) > 0
        ):
            warn(
                "object_hidden",
                f"'{obj['name']}' is in frame but hidden behind {names(view.get('occluded_by', []))}",
                [obj["name"]],
                "info",
            )
        if obj.get("renders_geometry") and obj.get("degenerate_axes") == 1:
            warn(
                "flattened_transform",
                f"'{obj['name']}' is scaled flat on one axis; normals and shading can break",
                [obj["name"]],
            )
        if obj.get("faces_without_material"):
            warn(
                "faces_without_material",
                f"'{obj['name']}' has {obj['faces_without_material']} faces without a material (they render default grey)",
                [obj["name"]],
            )
        if obj.get("role") == "subject" and (view.get("beyond_clip_end") or 0) > 0:
            warn(
                "beyond_clip",
                f"Part of '{obj['name']}' lies beyond the camera clip end and will not render",
                [obj["name"]],
            )
    hidden_geometry = [
        o["name"] for o in scene["objects"] if o["type"] in GEOMETRY_TYPES and not o["render_visible"]
    ]
    if hidden_geometry:
        warn(
            "hidden_geometry",
            f"{len(hidden_geometry)} geometry objects do not render: {names(hidden_geometry)}",
            hidden_geometry,
            "info",
        )
    for light in scene["lights"]:
        if not light.get("render_visible") and (light.get("energy") or 0) > 0:
            warn(
                "light_hidden",
                f"Light '{light['name']}' does not render: {'; '.join(light['hidden_by'])}",
                [light["name"]],
                "info",
            )
        elif light.get("aimed_at_subject") is False:
            warn(
                "light_misses_subject",
                f"Light '{light['name']}' points {light.get('angle_off_axis_deg')} degrees away from the subject",
                [light["name"]],
            )
        elif light.get("reaches_subject") == 0 and (light.get("facing_but_blocked") or 0) > 0:
            warn(
                "light_blocked",
                f"Light '{light['name']}' never reaches the visible subject: blocked by {names(light.get('blocked_by', []))}",
                [light["name"]],
            )
    lighting = lighting_summary(scene)
    ratio = lighting.get("key_to_fill")
    if ratio is not None and "fill" in lighting:
        if ratio < FLAT_RATIO:
            warn(
                "flat_lighting",
                f"Key '{lighting['key']}' and fill '{lighting['fill']}' are nearly equal on the visible subject "
                f"({ratio:.2f}:1); fine for catalogue shots, raise the key for more shape",
                severity="info",
            )
        elif ratio > HARSH_RATIO:
            warn("harsh_lighting", f"Key-to-fill ratio is {ratio:.1f}:1; shadow sides will be very dark")
    elif lighting.get("key") and lighting["ambient"] < 0.1 * lighting["ranked"][0][1]:
        warn(
            "no_fill",
            f"Only '{lighting['key']}' lights the subject and the world is dark; shadow sides will be black",
        )
    camera = scene["camera"] or {}
    if (scene.get("frame") or {}).get("camera_inside"):
        warn("camera_inside", f"The camera is inside '{scene['frame']['camera_inside']}'")
    dof = camera.get("dof") or {}
    distance = subject.get("distance")
    if dof.get("use") and distance:
        focus = dof.get("focus_distance")
        target = next((o for o in scene["objects"] if o["name"] == dof.get("focus_object")), None)
        if target is not None and camera.get("location"):
            focus = math.dist(target["location"], camera["location"])
        if focus and abs(focus - distance) > 0.25 * distance and (dof.get("fstop") or 99) < 5.6:
            warn(
                "out_of_focus",
                f"Depth of field focuses at {focus:.2f} but the subject is {distance:.2f} away (f/{dof['fstop']})",
            )
    radius = subject.get("radius")
    scale = (scene.get("units") or {}).get("scale_length") or 1.0
    if radius and not 0.005 <= radius * scale <= 500:
        warn("unit_scale", f"The subject is {2 * radius * scale:.3g} m across; check units and object scale")
    extra = [s["name"] for s in scene.get("scenes", []) if s["name"] != scene.get("scene")]
    if extra:
        warn(
            "extra_scenes",
            f"The file has other scenes: {names(extra)}; only '{scene.get('scene')}' was inspected",
            severity="info",
        )
    for image in scene["missing_images"]:
        if not image.get("used"):
            warn(
                "unused_missing_image",
                f"Unused image '{image['name']}' points to a missing file",
                severity="info",
            )
    animation = scene["animation"]
    for obj in animation.get("objects", []):
        if (
            obj.get("keys_after_end")
            and obj.get("key_range")
            and obj["key_range"][0] <= animation["frame_end"]
        ):
            warn(
                "animation_truncated",
                f"'{obj['name']}' has keys after frame_end {animation['frame_end']} (last key {obj['key_range'][1]:g}); "
                "the end of its animation will not render",
                [obj["name"]],
            )
    motion = animation.get("motion") or {}
    for name, track in motion.get("objects", {}).items():
        for start, stop, distance_moved in track.get("jumps", []):
            warn(
                "animation_jump", f"'{name}' jumps {distance_moved} between frames {start} and {stop}", [name]
            )
    visible_share = motion.get("subject_in_frame")
    if visible_share and min(visible_share) < 0.5:
        frames = [f for f, v in zip(motion["frames"], visible_share) if v < 0.5]
        warn(
            "subject_leaves_frame",
            f"The subject is mostly out of frame on sampled frames {frames[0]}-{frames[-1]}",
        )
    drivers = animation.get("python_drivers_not_evaluated")
    if drivers:
        warn(
            "python_drivers",
            f"{drivers} drivers use Python expressions; they were not evaluated (the inspector disables auto-run scripts)",
            severity="info",
        )
    return found


def technical_report_v2(scene, strict_contact=False):
    validate(scene)
    checks = gates(scene, strict_contact)
    passed = sum(check["passed"] for check in checks)
    return {
        "schema_version": 2,
        "kind": "technical",
        "passed": passed,
        "total": len(checks),
        "pass_rate": round(100 * passed / len(checks), 1),
        "checks": checks,
        "warnings": warnings(scene),
        "note": "Technical gates are not an aesthetic score. They are computed from scene geometry, not pixels.",
    }
