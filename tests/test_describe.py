import json
import math
import os
import random
from pathlib import Path

import pytest

from blender_quality.describe import color_name, describe, look_at_euler, to_markdown
from blender_quality.image_metrics import measure_file

FIXTURES = Path(__file__).parent / "fixtures"
INSPECTIONS = sorted(p.stem for p in (FIXTURES / "inspections").glob("*.json"))


def load(name):
    return json.loads((FIXTURES / "inspections" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", INSPECTIONS)
def test_markdown_snapshot(name):
    """The report is deterministic; set BQL_UPDATE_SNAPSHOTS=1 to accept intended wording changes."""
    text = to_markdown(describe(load(name)))
    snapshot = FIXTURES / "describe" / f"{name}.md"
    if os.environ.get("BQL_UPDATE_SNAPSHOTS") == "1":
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(text, encoding="utf-8", newline="\n")
    assert text == snapshot.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("variant", "fix_id", "code"),
    [
        ("camera_away", "subject_in_frame", "cam.rotation_euler = (1.2625, 0.0, 0.6202)"),
        (
            "hidden_collection",
            "renderable_geometry",
            "bpy.data.collections['Disabled for render'].hide_render = False",
        ),
        (
            "zero_scale_parent",
            "non_degenerate_world_transform",
            "bpy.data.objects['Collapsed parent'].scale = (1.0, 1.0, 1.0)",
        ),
        ("no_lights_unused_emission", "effective_illumination", "bpy.data.lights.new('Key light', 'AREA')"),
        ("floating", "floating", ".location.z -= 3.002"),
        (
            "keys_out_of_range",
            "animation_keys_in_range",
            "frame_start, bpy.context.scene.frame_end = 300, 400",
        ),
    ],
)
def test_first_fix_names_the_real_problem(variant, fix_id, code):
    report = describe(load(f"abstract-{variant}"))
    first = report["fixes"][0]
    assert first["id"] == fix_id
    assert code in first["python"]


def test_healthy_recipes_only_get_optional_advice():
    for recipe in ["product", "abstract", "interior"]:
        report = describe(load(recipe))
        assert report["failed_gates"] == []
        assert all(fix["priority"] >= 4 for fix in report["fixes"]), report["fixes"]


def test_report_explains_frame_subject_and_lights():
    report = describe(load("abstract"))
    assert report["frame"]["objects"][0] == {"name": "Backdrop floor", "share": 0.7975, "char": "A"}
    assert report["subject"]["placement"] == "middle-centre"
    assert report["subject"]["in_frame"] == 1.0
    roles = {light["name"]: light["role"] for light in report["lighting"]["lights"]}
    assert roles == {"Cool fill": "key", "Large warm key": "fill", "Edge separation": "accent"}
    materials = {m["name"]: m["looks"] for m in report["materials"]}
    assert materials == {"Brushed copper": "mid orange", "Charcoal stone": "near-black"}


def test_hidden_parts_of_the_subject_are_listed():
    report = describe(load("interior"))
    hidden = {item["name"]: item["behind"] for item in report["subject"]["mostly_hidden"]}
    assert hidden["Chair leg.001"] == ["Chair seat"]


def test_exposure_fixes_wait_for_the_gates():
    black = measure_file(FIXTURES / "renders" / "abstract-no_lights_unused_emission-preview.png")
    report = describe(load("abstract-no_lights_unused_emission"), black)
    ids = [fix["id"] for fix in report["fixes"]]
    assert ids[:2] == ["effective_illumination", "black_frame"]
    assert report["fixes"][1]["python"] is None  # more exposure cannot light an unlit scene
    assert "Fix the failed gates first" in report["fixes"][1]["action"]
    text = to_markdown(report)
    assert "## Exposure (measured on the render)" in text and "Brightness map" in text


def test_exposure_fix_when_the_scene_is_sound_but_dark():
    dark = measure_file(FIXTURES / "renders" / "abstract-hidden_collection-preview.png")
    dark["warnings"] = [w for w in dark["warnings"] if w["id"] == "underexposed"]
    report = describe(load("abstract"), dark)
    fix = next(item for item in report["fixes"] if item["id"] == "underexposed")
    assert fix["python"] == "bpy.context.scene.view_settings.exposure += 2.1"


def test_animation_section():
    report = describe(load("abstract-animated"))
    assert report["animation"]["frames"] == [1, 48]
    assert report["animation"]["motion"]["Copper orbit 3"]["path_length"] == pytest.approx(0.9945)
    assert "## Animation" in to_markdown(report)


def test_v1_inspections_are_rejected():
    with pytest.raises(ValueError, match="schema_version 2"):
        describe({"schema_version": 1})


def euler_matrix(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = (
        math.cos(rx),
        math.sin(rx),
        math.cos(ry),
        math.sin(ry),
        math.cos(rz),
        math.sin(rz),
    )
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]


def test_look_at_points_minus_z_at_the_target():
    rng = random.Random(7)
    for _ in range(500):
        origin = [rng.uniform(-9, 9) for _ in range(3)]
        target = [rng.uniform(-9, 9) for _ in range(3)]
        m = euler_matrix(*look_at_euler(origin, target))
        forward = [-m[0][2], -m[1][2], -m[2][2]]
        direction = [t - o for t, o in zip(target, origin)]
        length = math.sqrt(sum(d * d for d in direction))
        assert all(abs(f - d / length) < 1e-9 for f, d in zip(forward, direction))
        assert m[2][0] ** 2 + m[2][1] ** 2 + m[2][2] ** 2 == pytest.approx(1)
        assert abs(m[2][0]) < 1e-9  # camera x axis stays horizontal: no roll


def test_color_names():
    assert color_name([0.63, 0.23, 0.10]) == "mid orange"
    assert color_name([0.05, 0.05, 0.05]) == "near-black"
    assert color_name([0.1, 0.2, 0.8]) == "mid blue"
    assert color_name("texture") == "textured"


def test_missing_camera_gets_a_framing_camera():
    first = describe(load("abstract-no_camera"))["fixes"][0]
    assert first["id"] == "camera"
    assert "bpy.context.scene.camera = cam" in first["python"]
    pano = to_markdown(describe(load("abstract-pano_camera")))
    assert "framing is not analysed" in pano
