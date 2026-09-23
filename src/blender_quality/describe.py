"""Turn an inspection (and optionally render metrics) into a short report a model without vision can act on.

Everything here is deterministic and computed from the inspection facts: what the camera sees, what
is cut off or hidden, what floats, how the lights reach the subject, how the render is exposed, and a
prioritized list of fixes with the Blender Python that applies them.
"""

import math
import re

from .gates import lighting_summary, names, pct
from .scoring import technical_report

TARGET_KEY_IRRADIANCE = 6.0  # W/m2 on axis; about what the lab recipes' key lights deliver
FIT_MARGIN = 1.15


# ---------------------------------------------------------------- vector helpers (pure Python)


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def scale(a, s):
    return [x * s for x in a]


def norm(a):
    return math.sqrt(sum(x * x for x in a))


def unit(a):
    length = norm(a)
    return [x / length for x in a] if length > 1e-12 else [0.0, 0.0, 0.0]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def rounded(values, digits=3):
    return tuple(round(v, digits) + 0.0 for v in values)


def look_at_euler(origin, target):
    """XYZ Euler that points an object's -Z axis at target with +Y up, like to_track_quat('-Z', 'Y')."""
    back = unit(sub(origin, target))  # the object's +Z axis
    up = [0.0, 0.0, 1.0]
    if abs(back[2]) > 0.9999:
        up = [0.0, 1.0, 0.0]
    y_axis = unit(sub(up, scale(back, sum(u * b for u, b in zip(up, back)))))
    x_axis = cross(y_axis, back)
    # Rotation matrix columns are the object axes; decompose R = Rz * Ry * Rx.
    r20, r21, r22 = x_axis[2], y_axis[2], back[2]
    r10, r00 = x_axis[1], x_axis[0]
    ry = math.asin(max(-1.0, min(1.0, -r20)))
    if abs(math.cos(ry)) > 1e-6:
        rx = math.atan2(r21, r22)
        rz = math.atan2(r10, r00)
    else:  # gimbal lock: fold everything into rz
        rx = 0.0
        rz = math.atan2(-y_axis[0], y_axis[1])
    return [rx, ry, rz]


def fit_distance(radius, camera):
    """Distance at which a sphere of this radius fills the narrower field of view with a margin."""
    fovs = [f for f in (camera.get("hfov_deg"), camera.get("vfov_deg")) if f]
    if not fovs:
        return None
    half = math.radians(min(fovs)) / 2
    return radius / math.sin(half) * FIT_MARGIN


def third(x, y):
    column = "left" if x < 1 / 3 else ("centre" if x <= 2 / 3 else "right")
    row = "bottom" if y < 1 / 3 else ("middle" if y <= 2 / 3 else "top")
    return f"{row}-{column}"


def color_name(rgb):
    """Rough everyday name for a linear RGB base color."""
    if not isinstance(rgb, list):
        return "textured"
    srgb = [
        c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in (max(0.0, v) for v in rgb)
    ]
    high, low = max(srgb), min(srgb)
    light = (high + low) / 2
    tone = "dark" if light < 0.3 else ("light" if light > 0.7 else "mid")
    if high - low < 0.08:
        return {"dark": "near-black", "mid": "grey", "light": "off-white"}[tone]
    r, g, b = srgb
    if high == r:
        hue = 60 * (((g - b) / (high - low)) % 6)
    elif high == g:
        hue = 60 * ((b - r) / (high - low) + 2)
    else:
        hue = 60 * ((r - g) / (high - low) + 4)
    for limit, label in ((15, "red"), (45, "orange"), (70, "yellow"), (160, "green"), (200, "cyan"),
                         (260, "blue"), (300, "purple"), (340, "magenta"), (361, "red")):  # fmt: skip
        if hue < limit:
            return f"{tone} {label}"
    return tone


# ---------------------------------------------------------------- fixes


def obj_ref(name):
    return f"bpy.data.objects[{name!r}]"


def camera_fix(scene, reason, keep_location=True):
    camera, subject = scene["camera"], scene["subject"]
    center, radius = subject["center"], subject["radius"]
    location = camera["location"]
    distance = fit_distance(radius, camera)
    if distance is None:
        keep_location = True  # no field of view to fit (panoramic camera): only re-aim
    direction = unit(sub(location, center))
    if not keep_location:
        location = add(center, scale(direction, distance))
    rotation = look_at_euler(location, center)
    code = f"cam = {obj_ref(camera['name'])}; "
    if not keep_location:
        code += f"cam.location = {rounded(location)}; "
    code += f"cam.rotation_mode = 'XYZ'; cam.rotation_euler = {rounded(rotation, 4)}"
    action = f"Aim the camera at the subject centre {rounded(center)}"
    if not keep_location:
        action = f"Move the camera to {rounded(location)} ({distance:.2f} from the subject centre) and aim it at {rounded(center)}"
    return {"problem": reason, "action": action, "python": code}


def light_position(scene, side=-1.0, lift=0.8):
    """A classic key (side=-1, camera left) or fill (side=+1) position around the subject."""
    subject, camera = scene["subject"], scene["camera"]
    center, radius = subject["center"], subject["radius"]
    toward_camera = unit(sub(camera["location"], center)) if camera else [0.6, -0.8, 0.0]
    right = unit(cross(toward_camera, [0.0, 0.0, 1.0])) if camera else [1.0, 0.0, 0.0]
    right = scale(right, -1.0)  # cross(toward camera, up) points to the camera's left
    direction = unit(add(add(scale(toward_camera, 0.7), scale(right, 0.7 * side)), [0.0, 0.0, lift]))
    distance = max(3.0 * radius, 1.0)
    return add(center, scale(direction, distance)), distance


def add_light_fix(scene, problem, role="key", power_factor=1.0):
    position, distance = light_position(
        scene, side=-1.0 if role == "key" else 1.0, lift=0.8 if role == "key" else 0.3
    )
    power = round(TARGET_KEY_IRRADIANCE * math.pi * distance * distance * power_factor)
    rotation = look_at_euler(position, scene["subject"]["center"])
    name = "Key light" if role == "key" else "Fill light"
    code = (
        f"data = bpy.data.lights.new({name!r}, 'AREA'); data.energy = {power}; data.size = {max(1.0, round(distance / 3, 2))}; "
        f"obj = bpy.data.objects.new({name!r}, data); bpy.context.scene.collection.objects.link(obj); "
        f"obj.location = {rounded(position)}; obj.rotation_euler = {rounded(rotation, 4)}"
    )
    return {
        "problem": problem,
        "action": f"Add an area {role} light at {rounded(position)} aimed at the subject, about {power} W",
        "python": code,
    }


def roots_of(group, objects):
    """Group members whose parent is not also in the group (moving them moves their children)."""
    parents = {o["name"]: o.get("parent") for o in objects}
    return [n for n in group if parents.get(n) not in group]


def fixes_for(scene, report, metrics):
    fixes = []
    by_id = {c["id"]: c for c in report["checks"]}
    objects = scene["objects"]
    subject = scene["subject"]
    camera = scene["camera"]

    def fix(priority, key, problem, action, python=None):
        fixes.append(
            {"priority": priority, "id": key, "problem": problem, "action": action, "python": python}
        )

    failing = [c for c in report["checks"] if not c["passed"] and not c.get("blocked_by")]
    for check in failing:
        key, detail = check["id"], check["detail"]
        if key == "renderable_geometry":
            code = []
            for obj in objects:
                for reason in obj["hidden_by"]:
                    match = re.match(r"collection '(.+)' has hide_render on", reason)
                    if match:
                        code.append(f"bpy.data.collections[{match.group(1)!r}].hide_render = False")
                    elif re.match(r"collection '(.+)' is excluded", reason):
                        name = re.match(r"collection '(.+)' is excluded", reason).group(1)
                        code.append(f"# enable collection {name!r} in the view layer (untick 'exclude')")
                    elif reason == "object has hide_render on":
                        code.append(f"{obj_ref(obj['name'])}.hide_render = False")
                    elif reason == "camera ray visibility is off":
                        code.append(f"{obj_ref(obj['name'])}.visible_camera = True")
            action = "Make the geometry render again" if code else "Add geometry the camera can see"
            fix(
                1,
                key,
                f"Nothing the camera can see renders: {detail}",
                action,
                "; ".join(dict.fromkeys(code)) or None,
            )
        elif key == "camera":
            if subject:
                distance = fit_distance(subject["radius"], {"hfov_deg": 39.6, "vfov_deg": 27.0}) or 5.0
                location = add(subject["center"], scale(unit([0.6, -0.84, 0.48]), distance))
                rotation = look_at_euler(location, subject["center"])
                code = (
                    "cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera')); "
                    "bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam; "
                    f"cam.location = {rounded(location)}; cam.rotation_euler = {rounded(rotation, 4)}"
                )
                fix(
                    1,
                    key,
                    "The scene has no active camera",
                    f"Add a 50 mm camera at {rounded(location)} framing the subject",
                    code,
                )
            else:
                fix(1, key, "The scene has no active camera", "Add a camera and set it as scene.camera")
        elif key == "non_degenerate_world_transform":
            broken = [
                o
                for o in objects
                if o.get("renders_geometry") and (not o["finite"] or o["degenerate_axes"] >= 2)
            ]
            code, culprits = [], []
            for obj in broken:
                target = obj
                while target is not None and min(abs(s) for s in target["scale"]) > 1e-8:
                    parent = target.get("parent")
                    target = next((o for o in objects if o["name"] == parent), None) if parent else None
                target = target or obj
                if target["name"] not in culprits:
                    culprits.append(target["name"])
                    new_scale = tuple(1.0 if abs(s) <= 1e-8 else s for s in target["scale"])
                    code.append(f"{obj_ref(target['name'])}.scale = {rounded(new_scale)}")
            fix(1, key, detail, f"Give {names(culprits)} a non-zero scale", "; ".join(code))
        elif key == "subject_in_frame":
            if subject and camera:
                occluded = (subject.get("occluded") or 0) >= 0.95
                if occluded:
                    blockers = sorted(
                        {
                            b
                            for o in objects
                            if o["name"] in subject["objects"]
                            for b in (o.get("view") or {}).get("occluded_by", [])
                        }
                    )
                    code = "; ".join(f"{obj_ref(b)}.visible_camera = False" for b in blockers)
                    fix(
                        1,
                        key,
                        detail,
                        f"Move the camera to a clear line of sight, or hide {names(blockers)} from the camera only (keeps shadows)",
                        code,
                    )
                else:
                    item = camera_fix(scene, detail, keep_location=True)
                    fix(1, key, item["problem"], item["action"], item["python"])
            else:
                fix(1, key, detail, "Give the scene visible geometry to frame")
        elif key == "not_cropped_or_tiny":
            item = camera_fix(scene, detail, keep_location=False)
            fix(2, key, item["problem"], item["action"], item["python"])
        elif key == "effective_illumination":
            if subject:
                item = add_light_fix(scene, f"Nothing lights the subject: {detail}")
                fix(1, key, item["problem"], item["action"], item["python"])
            else:
                fix(1, key, f"Nothing lights the scene: {detail}", "Add a light or a non-black world")
        elif key == "materials":
            missing = [
                o["name"]
                for o in objects
                if o.get("renders_geometry") and o.get("material_count", 0) == 0 and o["camera_visible"]
            ]
            code = "mat = bpy.data.materials.new('Base'); " + "; ".join(
                f"{obj_ref(n)}.data.materials.append(mat)" for n in missing[:8]
            )
            fix(2, key, detail, f"Assign materials to {names(missing)}", code)
        elif key == "missing_images":
            fix(2, key, detail, "Relink the files (File > External Data > Find Missing Files) or pack them",
                "bpy.ops.file.find_missing_files(directory='PATH/TO/TEXTURES')")  # fmt: skip
        elif key == "resolution":
            fix(
                3,
                key,
                detail,
                "Render at least 256 x 256",
                "scene = bpy.context.scene; scene.render.resolution_x, scene.render.resolution_y = 1920, 1080; scene.render.resolution_percentage = 100",
            )
        elif key == "animation_keys_in_range":
            animation = scene["animation"]
            frames = [f for o in animation["objects"] if o.get("key_range") for f in o["key_range"]]
            code = None
            if frames:
                code = f"bpy.context.scene.frame_start, bpy.context.scene.frame_end = {int(math.floor(min(frames)))}, {int(math.ceil(max(frames)))}"
            fix(
                2,
                key,
                detail,
                "Make the frame range cover the keys (or move the keys into the range); delete non-finite keys",
                code,
            )
        elif key == "grounded":
            pass  # handled with the floating warning below
    for warning in report["warnings"]:
        key, message = warning["id"], warning["message"]
        if key == "floating":
            group = next(
                (g for g in scene["contacts"]["floating"] if g["objects"] == warning["objects"]), None
            )
            if group:
                roots = roots_of(group["objects"], objects)
                code = f"for name in {roots!r}: bpy.data.objects[name].location.z -= {group['gap']}"
                fix(
                    2 if by_id.get("grounded") else 3,
                    key,
                    message,
                    f"Lower {names(roots)} by {group['gap']} so they rest on '{group['above']}'",
                    code,
                )
        elif key == "subject_cut_off":
            item = camera_fix(scene, message, keep_location=False)
            fix(3, key, item["problem"], item["action"], item["python"])
        elif key == "small_subject":
            item = camera_fix(scene, message, keep_location=False)
            fix(3, key, item["problem"], item["action"], item["python"])
        elif key == "light_misses_subject":
            light = next(item for item in scene["lights"] if item["name"] == warning["objects"][0])
            rotation = look_at_euler(light["location"], subject["center"])
            fix(
                3,
                key,
                message,
                f"Aim '{light['name']}' at the subject",
                f"{obj_ref(light['name'])}.rotation_euler = {rounded(rotation, 4)}",
            )
        elif key == "light_blocked":
            light = next(item for item in scene["lights"] if item["name"] == warning["objects"][0])
            fix(3, key, message, f"Move '{light['name']}' so it has a clear line to the subject, or stop the blockers casting shadows",
                "; ".join(f"{obj_ref(b)}.visible_shadow = False" for b in light.get("blocked_by", [])))  # fmt: skip
        elif key == "no_fill":
            key_light = lighting_summary(scene).get("key")
            key_power = next(
                (light["energy"] for light in scene["lights"] if light["name"] == key_light), None
            )
            item = add_light_fix(scene, message, role="fill", power_factor=0.35)
            if key_power:
                item["action"] += f" (about a third of the key's {key_power:g} W)"
            fix(3, key, item["problem"], item["action"], item["python"])
        elif key == "harsh_lighting":
            summary = lighting_summary(scene)
            factor = summary["key_to_fill"] / 4
            fill = next(light for light in scene["lights"] if light["name"] == summary["fill"])
            fix(3, key, message, f"Raise '{fill['name']}' to about {fill['energy'] * factor:.0f} W for a 4:1 ratio",
                f"{obj_ref(fill['name'])}.data.energy = {fill['energy'] * factor:.0f}")  # fmt: skip
        elif key == "camera_inside":
            item = camera_fix(scene, message, keep_location=False)
            fix(2, key, item["problem"], item["action"], item["python"])
        elif key == "out_of_focus":
            fix(
                3,
                key,
                message,
                "Focus on the subject",
                f"{obj_ref(camera['name'])}.data.dof.focus_distance = {subject['distance']:.3f}",
            )
        elif key == "animation_truncated":
            obj = next(o for o in scene["animation"]["objects"] if o["name"] == warning["objects"][0])
            fix(
                3,
                key,
                message,
                "Extend the frame range to the last key",
                f"bpy.context.scene.frame_end = {int(math.ceil(obj['key_range'][1]))}",
            )
        elif key == "flattened_transform":
            fix(4, key, message, "Apply or fix the zero scale axis")
        elif key == "faces_without_material":
            fix(4, key, message, "Assign a material to every face")
        elif key == "flat_lighting":
            summary = lighting_summary(scene)
            key_light = next(light for light in scene["lights"] if light["name"] == summary["key"])
            fix(5, key, message, f"For more shape, double '{key_light['name']}' or halve '{summary['fill']}'",
                f"{obj_ref(key_light['name'])}.data.energy = {key_light['energy'] * 2:g}")  # fmt: skip
    if metrics:
        mean = (metrics.get("luminance") or {}).get("mean")
        # A dark or empty frame caused by a failed gate (camera away, nothing lit) is not an exposure
        # problem: turning exposure up would only hide it. Fix the gates, re-render, then re-measure.
        gates_first = bool(failing)
        for warning in metrics.get("warnings", []):
            key = warning["id"]
            if key in {"near_uniform", "empty_frame"} or (
                gates_first and key in {"underexposed", "black_frame", "overexposed"}
            ):
                fix(2, key, warning["message"], "Fix the failed gates first (the subject is out of frame, hidden or unlit), then re-render and re-measure" if gates_first
                    else "The subject is missing, hidden or unlit even though the gates pass; check what the camera sees above")  # fmt: skip
            elif key in {"underexposed", "black_frame"} and mean is not None:
                stops = 3.0 if mean < 0.02 else min(3.0, max(0.5, 2.2 * math.log2(0.35 / mean)))
                fix(2 if key == "black_frame" else 3, key, warning["message"], f"Brighten by about {stops:.1f} stops (or add light), then re-render and re-measure",
                    f"bpy.context.scene.view_settings.exposure += {stops:.1f}")  # fmt: skip
            elif key == "overexposed" and mean is not None:
                stops = max(0.5, min(3.0, 2.2 * math.log2(mean / 0.4))) if mean > 0.4 else 0.5
                fix(3, key, warning["message"], f"Darken by about {stops:.1f} stops or lower the brightest light",
                    f"bpy.context.scene.view_settings.exposure -= {stops:.1f}")  # fmt: skip
            elif key == "crushed_shadows":
                fix(3, key, warning["message"], "Add fill light or raise the world strength")
            elif key == "low_contrast":
                fix(4, key, warning["message"], "Separate key and fill more, or darken the background")
    fixes.sort(key=lambda f: f["priority"])
    return fixes


# ---------------------------------------------------------------- report


def frame_map(frame, rows=24):
    if not frame:
        return []
    grid = frame["rows"]
    step = max(1, round(len(grid) / rows))
    return [grid[i] for i in range(step // 2, len(grid), step)]


def describe(scene, metrics=None, strict_contact=False):
    if scene.get("schema_version") != 2:
        raise ValueError(
            "describe needs an inspection with schema_version 2; re-run `blender-quality inspect`"
        )
    report = technical_report(scene, strict_contact=strict_contact)
    subject, camera, frame = scene["subject"], scene["camera"], scene.get("frame")
    views = {o["name"]: o for o in scene["objects"]}
    out = {
        "scene": scene["scene"],
        "blender": scene.get("blender_version"),
        "engine": scene.get("engine"),
        "resolution": scene["resolution"],
        "gates": {"passed": report["passed"], "total": report["total"]},
        "failed_gates": [
            {
                "id": c["id"],
                "detail": c["detail"],
                **({"blocked_by": c["blocked_by"]} if c.get("blocked_by") else {}),
            }
            for c in report["checks"]
            if not c["passed"]
        ],
        "warnings": report["warnings"],
    }
    if camera:
        out["camera"] = {
            "name": camera["name"],
            "type": camera.get("type"),
            "lens_mm": camera.get("lens_mm"),
            "location": camera.get("location"),
            "looking": camera.get("forward"),
            "fov_deg": [camera.get("hfov_deg"), camera.get("vfov_deg")],
        }
    if frame:
        coverage = sorted(
            (
                (o["name"], o["view"]["coverage"])
                for o in scene["objects"]
                if (o.get("view") or {}).get("coverage")
            ),
            key=lambda item: -item[1],
        )
        legend = {name: char for char, name in frame["legend"].items()}
        out["frame"] = {
            "background": frame["background"],
            "objects": [{"name": n, "share": c, "char": legend.get(n, "#")} for n, c in coverage],
            "map": frame_map(frame),
        }
    if subject:
        share = {n: ((views[n].get("view") or {}).get("coverage") or 0) for n in subject["objects"]}
        info = {
            "objects": sorted(subject["objects"], key=lambda n: (-share[n], n)),
            "environment": subject["environment"],
            "chosen_by": subject["method"],
            "center": subject["center"],
            "size": [round(b - a, 3) for a, b in zip(subject["bbox_min"], subject["bbox_max"])],
        }
        for key in (
            "in_frame",
            "coverage",
            "occluded",
            "cut_off",
            "center_screen",
            "distance",
            "screen_bbox",
        ):
            if key in subject:
                info[key] = subject[key]
        if subject.get("center_screen"):
            info["placement"] = third(*subject["center_screen"])
        hidden = [
            (n, views[n]["view"]["occluded"], views[n]["view"].get("occluded_by", []))
            for n in subject["objects"]
            if ((views[n].get("view") or {}).get("occluded") or 0) >= 0.5
        ]
        info["mostly_hidden"] = [{"name": n, "hidden": h, "behind": b} for n, h, b in hidden]
        out["subject"] = info
    out["grounding"] = {
        "floating": scene["contacts"]["floating"],
        "tolerance": scene["contacts"].get("tolerance"),
        "checked": sum(1 for o in scene["objects"] if "support" in o),
    }
    summary = lighting_summary(scene)
    out["lighting"] = {
        "lights": [
            {
                "name": light["name"],
                "type": light["type"],
                "energy": light.get("energy"),
                "color": color_name(light.get("color")),
                "reaches_subject": light.get("reaches_subject"),
                "irradiance": light.get("irradiance"),
                "aimed_at_subject": light.get("aimed_at_subject"),
                "role": _light_role(light, summary),
                "blocked_by": light.get("blocked_by", []),
            }
            for light in scene["lights"]
        ],
        "key": summary.get("key"),
        "fill": summary.get("fill"),
        "key_to_fill": round(summary["key_to_fill"], 2) if summary.get("key_to_fill") else None,
        "world": {
            k: scene["world"].get(k) for k in ("name", "strength", "radiance", "textured", "film_transparent")
        },
        "emissive_materials": scene["illumination"].get("emissive_materials", []),
    }
    subject_names = set(subject["objects"]) if subject else set()
    out["materials"] = [
        {
            "name": m["name"],
            "looks": color_name(m.get("base_color")),
            "metallic": m.get("metallic"),
            "roughness": m.get("roughness"),
            "emission": bool(m.get("emission")),
            "see_through": m.get("see_through"),
            "on": m["users"],
        }
        for m in scene["materials"]
        if subject_names & set(m["users"]) or not subject_names
    ]
    animation = scene["animation"]
    if animation.get("objects"):
        out["animation"] = {
            "frames": [animation["frame_start"], animation["frame_end"]],
            "fps": animation.get("fps"),
            "animated": [
                {"name": o["name"], "channels": o["channels"], "key_range": o["key_range"]}
                for o in animation["objects"]
            ],
            "motion": {
                name: {k: track[k] for k in ("path_length", "max_speed")}
                for name, track in (animation.get("motion") or {}).get("objects", {}).items()
            },
            "subject_in_frame_min": min(
                (animation.get("motion") or {}).get("subject_in_frame") or [None], key=_none_last
            ),
        }
    if metrics:
        out["exposure"] = {
            "luminance": metrics.get("luminance"),
            "clipped_highlights": metrics.get("clipped_highlights"),
            "crushed_shadows": metrics.get("crushed_shadows"),
            "detail_center": metrics.get("detail_center"),
            "warnings": metrics.get("warnings", []),
            "ascii": metrics.get("ascii", []),
        }
    out["fixes"] = fixes_for(scene, report, metrics)
    return out


def _light_role(light, summary):
    if light["name"] == summary.get("key"):
        return "key"
    if light["name"] == summary.get("fill"):
        return "fill"
    angle = light.get("angle_to_camera_deg")
    if angle is not None and angle > 110:
        return "rim/back"
    if (light.get("irradiance") or 0) > 0:
        return "accent"
    return "no effect on the visible subject"


def to_markdown(d):
    lines = [f"# Scene report: {d['scene']}", ""]
    lines.append(
        f"Blender {d['blender']}, {d['engine']} {d['resolution'][0]} x {d['resolution'][1]}. "
        f"Gates: **{d['gates']['passed']}/{d['gates']['total']} passed**, {len(d['warnings'])} warnings."
    )
    lines.append("")
    if d["fixes"]:
        urgent = any(item["priority"] <= 3 for item in d["fixes"])
        lines += ["## Fix first" if urgent else "## Optional improvements", ""]
        for number, item in enumerate(d["fixes"], 1):
            lines.append(f"{number}. **{item['problem']}** {item['action']}.")
            if item.get("python"):
                lines.append(f"   `{item['python']}`")
        lines.append("")
    if d["failed_gates"]:
        lines += ["## Failed gates", ""]
        for gate in d["failed_gates"]:
            text = gate["detail"] or (
                "blocked by " + ", ".join(gate["blocked_by"]) if gate.get("blocked_by") else ""
            )
            lines.append(f"- `{gate['id']}`: {text}")
        lines.append("")
    camera = d.get("camera")
    lines += ["## What the camera sees", ""]
    if camera and camera.get("type") == "PANO":
        lines.append(
            f"Panoramic camera '{camera['name']}' at {camera.get('location')}: framing is not analysed."
        )
    elif camera:
        lines.append(
            f"Camera '{camera['name']}' ({camera['type']}, {camera['lens_mm']} mm) at {camera['location']}, "
            f"looking along {camera['looking']}, field of view {camera['fov_deg'][0]} x {camera['fov_deg'][1]} degrees."
        )
    else:
        lines.append("No active camera.")
    frame = d.get("frame")
    if frame:
        lines.append(f"Empty background: {pct(frame['background'])} of the frame.")
        lines += ["", "```text", *frame["map"], "```", ""]
        lines.append(
            "Legend: "
            + "; ".join(f"`{o['char']}` {o['name']} {pct(o['share'])}" for o in frame["objects"][:12])
            + ("; `.` background" if frame["background"] else "")
        )
    subject = d.get("subject")
    if subject:
        lines += ["", "## Subject", ""]
        lines.append(
            f"{names(subject['objects'], 6)} (chosen by {subject['chosen_by']}), size {subject['size']} around {subject['center']}."
        )
        if "in_frame" in subject:
            text = f"{pct(subject['in_frame'])} of its surface is in frame and it fills {pct(subject.get('coverage') or 0)} of the image"
            if subject.get("placement"):
                text += f", centred {subject['placement']} at {subject['center_screen']}"
            text += (
                f"; {pct(subject.get('occluded') or 0)} of the in-frame part is hidden behind other objects."
            )
            lines.append(text)
            if subject.get("cut_off"):
                lines.append(f"Cut off at the {', '.join(subject['cut_off'])} edge.")
        for item in subject.get("mostly_hidden", []):
            lines.append(
                f"- '{item['name']}' is {pct(item['hidden'])} hidden behind {names(item['behind'])}."
            )
        if subject["environment"]:
            lines.append(f"Treated as environment, not subject: {names(subject['environment'])}.")
    floating = d["grounding"]["floating"]
    lines += ["", "## Grounding", ""]
    if floating:
        for group in floating:
            lines.append(f"- {names(group['objects'])} float {group['gap']} above '{group['above']}'.")
    elif not d["grounding"].get("checked"):
        lines.append("No geometry with surface area to check.")
    else:
        lines.append(
            f"Every object group rests on or touches something (tolerance {d['grounding']['tolerance']})."
        )
    lighting = d["lighting"]
    lines += ["", "## Lighting", ""]
    for light in lighting["lights"]:
        reach = light["reaches_subject"]
        reach_text = "n/a" if reach is None else pct(reach)
        text = (
            f"- '{light['name']}' ({light['type']}, {light['energy']} W, {light['color']}): {light['role']}, "
            f"lights {reach_text} of the visible subject, about {light['irradiance']} W/m2"
        )
        if light["aimed_at_subject"] is False:
            text += ", points away from the subject"
        if light["blocked_by"]:
            text += f", partly blocked by {names(light['blocked_by'], 2)}"
        lines.append(text + ".")
    if lighting["key_to_fill"]:
        lines.append(f"Key-to-fill ratio about {lighting['key_to_fill']}:1.")
    world = lighting["world"]
    lines.append(
        f"World '{world['name']}': strength {world['strength']}"
        + (", textured" if world.get("textured") else f", radiance {world.get('radiance')}")
        + (", transparent film" if world.get("film_transparent") else "")
        + "."
    )
    if lighting["emissive_materials"]:
        lines.append(f"Emissive materials on visible objects: {names(lighting['emissive_materials'])}.")
    if d["materials"]:
        lines += ["", "## Materials", ""]
        for material in d["materials"]:
            parts = [material["looks"]]
            if material["metallic"] is not None:
                parts.append(f"metallic {material['metallic']}")
            if material["roughness"] is not None:
                parts.append(f"roughness {material['roughness']}")
            if material["emission"]:
                parts.append("emissive")
            if material["see_through"]:
                parts.append("see-through")
            lines.append(
                f"- '{material['name']}': {', '.join(str(p) for p in parts)} (on {names(material['on'], 3)})."
            )
    animation = d.get("animation")
    if animation:
        lines += ["", "## Animation", ""]
        lines.append(f"Frames {animation['frames'][0]}-{animation['frames'][1]} at {animation['fps']} fps.")
        for obj in animation["animated"]:
            motion = animation["motion"].get(obj["name"])
            text = f"- '{obj['name']}': {', '.join(obj['channels'])} keyed on frames {obj['key_range']}"
            if motion:
                text += f", travels {motion['path_length']} (max speed {motion['max_speed']}/s)"
            lines.append(text + ".")
        if animation.get("subject_in_frame_min") is not None:
            lines.append(
                f"Lowest share of the subject in frame over the animation: {pct(animation['subject_in_frame_min'])}."
            )
    exposure = d.get("exposure")
    if exposure and exposure.get("luminance"):
        lum = exposure["luminance"]
        lines += ["", "## Exposure (measured on the render)", ""]
        lines.append(
            f"Mean luminance {lum['mean']}, spread {lum['std']}, 2-98% range {lum['p2']}-{lum['p98']}, "
            f"{pct(exposure['clipped_highlights'])} clipped, {pct(exposure['crushed_shadows'])} crushed."
        )
        if exposure.get("detail_center"):
            lines.append(
                f"Visual detail is centred at {exposure['detail_center']} ({third(*_flip(exposure['detail_center']))})."
            )
        for warning in exposure["warnings"]:
            lines.append(f"- {warning['message']}.")
        if exposure.get("ascii"):
            lines += [
                "",
                "Brightness map (dark ` ` to bright `@`):",
                "",
                "```text",
                *exposure["ascii"],
                "```",
            ]
    if d["warnings"]:
        lines += ["", "## Warnings", ""]
        for warning in d["warnings"]:
            lines.append(f"- ({warning['severity']}) {warning['message']}.")
    return "\n".join(lines).rstrip() + "\n"


def _none_last(value):
    return 1.0 if value is None else value


def _flip(point):
    """Image metrics use y down; the thirds helper uses y up like the camera frame."""
    return point[0], 1 - point[1]
