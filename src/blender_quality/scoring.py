import math

from .gates import technical_report_v2

RUBRIC = {
    "brief": "Does the result satisfy the subject, style and deliverable?",
    "composition": "Is the silhouette readable, framing intentional and hierarchy clear?",
    "geometry": "Are proportions, intersections and edge treatments convincing?",
    "materials": "Are scale, roughness, variation and material response coherent?",
    "lighting": "Do light, shadows, contrast and color support the subject?",
    "finish": "Does the image avoid distracting artifacts and feel complete?",
}
PLACEHOLDER_REVIEWERS = {"your_name", "your name", "reviewer", "name"}
V1_FIELDS = {"objects": list, "camera": (str, type(None)), "illumination": bool, "missing_images": list}
V1_OBJECT_FIELDS = ("type", "hide_render", "finite", "scale", "material_count")


def _check_fields(data, fields, where):
    for key, kind in fields.items():
        if key not in data:
            raise ValueError(f"{where} is missing the required field '{key}'")
        if not isinstance(data[key], kind):
            raise ValueError(f"{where} field '{key}' has the wrong type ({type(data[key]).__name__})")


def _validate_v1(scene):
    _check_fields(scene, V1_FIELDS, "inspection")
    resolution = scene.get("resolution")
    if not (isinstance(resolution, list) and len(resolution) == 2):
        raise ValueError("inspection field 'resolution' must be [width, height]")
    for index, obj in enumerate(scene["objects"]):
        if not isinstance(obj, dict):
            raise ValueError(f"inspection objects[{index}] is not an object")
        for key in V1_OBJECT_FIELDS:
            if key not in obj:
                raise ValueError(f"inspection objects[{index}] is missing '{key}'")


def technical_report(scene, strict_contact=False):
    """Gates for an inspection. Schema 1 reports are scored exactly as before; schema 2 adds
    camera, visibility, contact and lighting gates plus advisory warnings (see gates.py)."""
    if not isinstance(scene, dict):
        raise ValueError("inspection JSON must be an object")
    if scene.get("schema_version") == 2:
        return technical_report_v2(scene, strict_contact)
    if scene.get("schema_version") != 1:
        raise ValueError(f"Unsupported inspection schema {scene.get('schema_version')!r}")
    _validate_v1(scene)
    objects = scene["objects"]
    meshes = [obj for obj in objects if obj["type"] == "MESH" and not obj["hide_render"]]
    checks = [
        ("visible_geometry", bool(meshes), "At least one render-visible mesh"),
        ("camera", bool(scene["camera"]), "An active render camera exists"),
        (
            "illumination",
            bool(scene["illumination"]),
            "A light, emitting material or nonzero world is present",
        ),
        (
            "finite_transforms",
            all(obj["finite"] for obj in objects),
            "Object transforms contain no NaN or infinity",
        ),
        (
            "nonzero_mesh_scale",
            all(min(abs(v) for v in obj["scale"]) > 1e-8 for obj in meshes),
            "Render-visible meshes have nonzero scale",
        ),
        (
            "materials",
            bool(meshes) and all(obj["material_count"] > 0 for obj in meshes),
            "Render-visible meshes have assigned materials",
        ),
        ("missing_images", not scene["missing_images"], "No missing file-backed images"),
        (
            "resolution",
            scene["resolution"][0] >= 256 and scene["resolution"][1] >= 256,
            "Effective render resolution is at least 256 x 256",
        ),
    ]
    passed = sum(bool(ok) for _, ok, _ in checks)
    return {
        "schema_version": 1,
        "kind": "technical",
        "passed": passed,
        "total": len(checks),
        "pass_rate": round(100 * passed / len(checks), 1),
        "checks": [{"id": key, "passed": bool(ok), "description": desc} for key, ok, desc in checks],
        "note": "Technical gates are not an aesthetic score. Camera presence does not prove good framing.",
    }


def human_report(ratings):
    if not isinstance(ratings, dict):
        raise ValueError("ratings JSON must be an object")
    scores = ratings.get("scores", {})
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
        raise ValueError("Supply every rubric dimension exactly once: " + ", ".join(RUBRIC))
    for key, value in scores.items():
        if value is None:
            raise ValueError(
                f"{key} has no score yet; replace every null in the rubric with a number from 0 to 5"
            )
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 5
        ):
            raise ValueError(f"{key} must be a finite number from 0 to 5")
    reviewer = ratings.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("A reviewer identifier is required")
    if reviewer.strip().lower() in PLACEHOLDER_REVIEWERS:
        raise ValueError(f"Replace the placeholder reviewer {reviewer!r} with a real reviewer identifier")
    if not isinstance(ratings.get("evidence"), str) or not ratings["evidence"].strip():
        raise ValueError("An evidence filename or URL is required")
    return {
        "schema_version": 1,
        "kind": "human",
        "reviewer": reviewer.strip(),
        "evidence": ratings["evidence"],
        "scores": scores,
        "score": round(sum(scores.values()) / 30 * 100, 1),
        "notes": ratings.get("notes", ""),
        "note": "Subjective human rating. Compare only matched briefs, budgets and review conditions.",
    }
