"""Schema v2 gates and warnings, tested on inspections recorded from real Blender 5.2 scenes."""

import copy
import json
from pathlib import Path

import pytest

from blender_quality.gates import lighting_summary
from blender_quality.scoring import technical_report

FIXTURES = Path(__file__).parent / "fixtures" / "inspections"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def primary_failures(report):
    return {c["id"] for c in report["checks"] if not c["passed"] and not c.get("blocked_by")}


def check(report, key):
    return next(c for c in report["checks"] if c["id"] == key)


def warning_ids(report):
    return {w["id"] for w in report["warnings"]}


@pytest.mark.parametrize("recipe", ["product", "abstract", "interior"])
def test_recipes_pass_every_v2_gate(recipe):
    report = technical_report(load(recipe))
    assert (report["passed"], report["total"]) == (10, 10)
    strict = technical_report(load(recipe), strict_contact=True)
    assert (strict["passed"], strict["total"]) == (11, 11)
    assert "floating" not in warning_ids(report)


@pytest.mark.parametrize(
    ("variant", "gate", "evidence"),
    [
        ("camera_away", "subject_in_frame", "behind the camera"),
        ("hidden_collection", "renderable_geometry", "collection 'Disabled for render' has hide_render on"),
        ("zero_scale_parent", "non_degenerate_world_transform", "parent 'Collapsed parent'"),
        ("no_lights_unused_emission", "effective_illumination", "'Unused glow'"),
        ("keys_out_of_range", "animation_keys_in_range", "frames 300-400, outside 1-250"),
    ],
)
def test_each_sabotage_fails_exactly_its_gate(variant, gate, evidence):
    report = technical_report(load(f"abstract-{variant}"))
    assert primary_failures(report) == {gate}
    assert evidence in check(report, gate)["detail"]
    assert report["passed"] < report["total"]


def test_blocked_gates_name_their_cause():
    report = technical_report(load("abstract-hidden_collection"))
    assert check(report, "subject_in_frame")["blocked_by"] == ["renderable_geometry"]
    assert check(report, "materials")["blocked_by"] == ["renderable_geometry"]
    zero = technical_report(load("abstract-zero_scale_parent"))
    assert check(zero, "subject_in_frame")["blocked_by"] == ["non_degenerate_world_transform"]


def test_floating_is_a_warning_or_a_strict_gate():
    inspection = load("abstract-floating")
    report = technical_report(inspection)
    assert primary_failures(report) == set()
    floating = next(w for w in report["warnings"] if w["id"] == "floating")
    assert floating["objects"] == ["Copper orbit 1", "Copper orbit 2", "Copper orbit 3"]
    assert "3.002" in floating["message"] and "'Exhibition plinth'" in floating["message"]
    assert "subject_cut_off" in warning_ids(report)
    assert primary_failures(technical_report(inspection, strict_contact=True)) == {"grounded"}


def test_legit_edits_and_animation_pass():
    for name in ["abstract-relight", "abstract-animated"]:
        report = technical_report(load(name), strict_contact=True)
        assert report["passed"] == report["total"], name


def test_v1_false_positives_are_now_caught():
    """The five scenes that scored 8/8 under schema 1 all fail or warn under schema 2."""
    for variant in ["camera_away", "hidden_collection", "zero_scale_parent", "no_lights_unused_emission"]:
        assert technical_report(load(f"abstract-{variant}"))["passed"] < 10
    assert "floating" in warning_ids(technical_report(load("abstract-floating")))


def edited(name="abstract"):
    return copy.deepcopy(load(name))


def test_light_pointing_away_is_reported():
    scene = edited()
    scene["lights"][0].update(aimed_at_subject=False, angle_off_axis_deg=120.0)
    assert "light_misses_subject" in warning_ids(technical_report(scene))


def test_all_lights_missing_the_subject_fails_illumination():
    scene = edited()
    scene["world"].update(radiance=0.0, strength=0.0)
    for light in scene["lights"]:
        light.update(reaches_subject=0.0, facing_but_blocked=0.4, blocked_by=["Box"], irradiance=0.0)
    report = technical_report(scene)
    assert primary_failures(report) == {"effective_illumination"}
    assert "blocked by 'Box'" in check(report, "effective_illumination")["detail"]
    assert "light_blocked" in warning_ids(report)


def test_tiny_and_cropped_subjects_fail():
    scene = edited()
    scene["subject"]["coverage"] = 0.002
    assert primary_failures(technical_report(scene)) == {"not_cropped_or_tiny"}
    scene = edited()
    scene["subject"].update(in_frame=0.2, cut_off=["left", "top"])
    report = technical_report(scene)
    assert "only 20.0% of the subject" in check(report, "not_cropped_or_tiny")["detail"]
    assert "subject_cut_off" in warning_ids(report)
    scene = edited()
    scene["subject"]["coverage"] = 0.03
    assert "small_subject" in warning_ids(technical_report(scene))


def test_hidden_subject_fails_framing():
    scene = edited()
    scene["subject"]["occluded"] = 0.99
    report = technical_report(scene)
    assert primary_failures(report) == {"subject_in_frame"}
    assert "hidden behind" in check(report, "subject_in_frame")["detail"]


def test_only_used_missing_images_fail():
    scene = edited()
    scene["missing_images"] = [{"name": "old.png", "filepath": "//old.png", "used": False}]
    report = technical_report(scene)
    assert check(report, "missing_images")["passed"]
    assert "unused_missing_image" in warning_ids(report)
    scene["missing_images"][0]["used"] = True
    assert primary_failures(technical_report(scene)) == {"missing_images"}


def test_non_finite_keys_fail_animation_gate():
    scene = edited("abstract-animated")
    scene["animation"]["objects"][0]["non_finite_keys"] = 2
    report = technical_report(scene)
    assert "2 non-finite keys" in check(report, "animation_keys_in_range")["detail"]


def test_truncated_animation_and_jumps_warn():
    scene = edited("abstract-animated")
    scene["animation"]["objects"][0].update(keys_after_end=3, key_range=[1.0, 60.0])
    scene["animation"]["motion"]["objects"]["Copper orbit 3"]["jumps"] = [[23, 26, 4.0]]
    scene["animation"]["motion"]["subject_in_frame"][10:14] = [0.1, 0.0, 0.0, 0.2]
    ids = warning_ids(technical_report(scene))
    assert {"animation_truncated", "animation_jump", "subject_leaves_frame"} <= ids


def test_lighting_ratio_warnings():
    scene = edited()
    summary = lighting_summary(scene)
    assert summary["key"] == "Cool fill" and summary["fill"] == "Large warm key"
    assert "flat_lighting" in warning_ids(technical_report(scene))
    scene["lights"][1]["irradiance"] = 20.0
    assert "harsh_lighting" in warning_ids(technical_report(scene))
    for light in scene["lights"][1:]:
        light["irradiance"] = 0.0
    scene["world"]["radiance"] = 0.0
    assert "no_fill" in warning_ids(technical_report(scene))


def test_camera_warnings():
    scene = edited()
    scene["camera"]["dof"].update(use=True, focus_distance=2.0, fstop=1.8)
    scene["frame"]["camera_inside"] = "Back wall"
    scene["units"]["scale_length"] = 1000.0
    assert {"out_of_focus", "camera_inside", "unit_scale"} <= warning_ids(technical_report(scene))


def test_partial_v2_inspection_is_rejected():
    with pytest.raises(ValueError, match="missing the required field 'lights'"):
        technical_report({"schema_version": 2, "objects": [], "camera": None, "subject": None})
    scene = edited()
    del scene["objects"][0]["degenerate_axes"]
    with pytest.raises(ValueError, match=r"objects\[0\] is missing 'degenerate_axes'"):
        technical_report(scene)


def test_scenes_without_a_usable_camera():
    no_camera = technical_report(load("abstract-no_camera"))
    assert primary_failures(no_camera) == {"camera"}
    assert check(no_camera, "subject_in_frame")["blocked_by"] == ["camera"]
    pano = technical_report(load("abstract-pano_camera"))
    assert pano["passed"] == pano["total"]
    assert check(pano, "subject_in_frame")["detail"] == "not analysed: panoramic camera"
    empty = technical_report(load("abstract-empty"))
    assert primary_failures(empty) == {"renderable_geometry", "camera"}
    assert check(empty, "renderable_geometry")["detail"] == "the scene has no geometry objects at all"
