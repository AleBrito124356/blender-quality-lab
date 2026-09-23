"""End-to-end checks against a real Blender. Run with `python -m pytest -m blender`.

Builds the three recipes, derives the sabotaged variants with sabotage.py, inspects everything
through the CLI (isolated Blender) and compares with the recorded fixtures in tests/fixtures,
which the pure-Python tests use without Blender. Set BQL_UPDATE_FIXTURES=1 to re-record them.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from blender_quality import cli
from blender_quality.runner import BlenderError, find_blender, run_blender
from blender_quality.scoring import technical_report

pytestmark = pytest.mark.blender
HERE = Path(__file__).parent
FIXTURES = HERE.parent / "fixtures" / "inspections"
RECIPES = ["product", "abstract", "interior"]
VARIANTS = {
    "camera_away": "subject_in_frame",
    "floating": None,
    "hidden_collection": "renderable_geometry",
    "zero_scale_parent": "non_degenerate_world_transform",
    "no_lights_unused_emission": "effective_illumination",
    "relight": None,
    "animated": None,
    "keys_out_of_range": "animation_keys_in_range",
}

try:
    BLENDER = find_blender().path
except BlenderError:
    BLENDER = None


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    root = tmp_path_factory.mktemp("lab")
    scenes = {}
    for recipe in RECIPES:
        assert cli.main(["build", recipe, "--output", str(root / recipe), "--blender", BLENDER]) == 0
        scenes[recipe] = root / recipe / f"{recipe}.blend"
    for variant in VARIANTS:
        target = root / f"abstract-{variant}.blend"
        run_blender(BLENDER, HERE / "sabotage.py", [target, variant], blend_file=scenes["abstract"])
        scenes[f"abstract-{variant}"] = target
    inspections = {}
    for name, blend in scenes.items():
        output = root / f"{name}.json"
        assert cli.main(["inspect", str(blend), "--output", str(output), "--blender", BLENDER]) == 0
        inspections[name] = json.loads(output.read_text(encoding="utf-8"))
        if os.environ.get("BQL_UPDATE_FIXTURES") == "1":
            FIXTURES.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output, FIXTURES / f"{name}.json")
    return {"root": root, "scenes": scenes, "inspections": inspections}


def primary_failures(report):
    return {c["id"] for c in report["checks"] if not c["passed"] and not c.get("blocked_by")}


def stable_facts(inspection):
    """Facts that must not drift between runs (the .blend hash and timings do)."""
    subject = inspection["subject"] or {}
    return {
        "scenes": [s["name"] for s in inspection["scenes"]],
        "objects": sorted(o["name"] for o in inspection["objects"]),
        "render_visible": sorted(o["name"] for o in inspection["objects"] if o["render_visible"]),
        "subject": subject.get("objects"),
        "in_frame": round(subject.get("in_frame") or 0, 2),
        "coverage": round(subject.get("coverage") or 0, 2),
        "floating": [(g["objects"], round(g["gap"], 2)) for g in inspection["contacts"]["floating"]],
        "lights": [
            (light["name"], round(light.get("reaches_subject") or 0, 1)) for light in inspection["lights"]
        ],
        "gates": [c["passed"] for c in technical_report(inspection)["checks"]],
    }


@pytest.mark.parametrize("recipe", RECIPES)
def test_recipe_files_hold_only_the_recipe_scene(lab, recipe, tmp_path):
    probe = tmp_path / "probe.json"
    run_blender(BLENDER, HERE / "probe_datablocks.py", [probe], blend_file=lab["scenes"][recipe])
    data = json.loads(probe.read_text(encoding="utf-8"))
    assert data["scenes"] == [f"QualityLab_{recipe}"]
    assert not {"Cube", "Camera", "Light"} & set(data["objects"])
    assert "Material" not in data["materials"]
    assert data["cameras"] == ["Editorial camera"]


@pytest.mark.parametrize("recipe", RECIPES)
def test_recipes_pass_every_gate_even_strict_contact(lab, recipe):
    report = technical_report(lab["inspections"][recipe], strict_contact=True)
    assert report["passed"] == report["total"], [c for c in report["checks"] if not c["passed"]]


@pytest.mark.parametrize("variant", VARIANTS)
def test_each_sabotage_fails_exactly_its_gate(lab, variant):
    inspection = lab["inspections"][f"abstract-{variant}"]
    expected = {VARIANTS[variant]} if VARIANTS[variant] else set()
    assert primary_failures(technical_report(inspection)) == expected
    if variant == "floating":
        assert primary_failures(technical_report(inspection, strict_contact=True)) == {"grounded"}


def test_layered_action_keys_are_read(lab):
    animation = lab["inspections"]["abstract-animated"]["animation"]
    animated = {o["name"]: o for o in animation["objects"]}
    assert animated["Copper orbit 3"]["channels"] == ["location"]
    assert animated["Copper orbit 3"]["key_range"] == [1.0, 48.0]
    assert animated["Editorial camera"]["keyframes"] == 6
    bob = animation["motion"]["objects"]["Copper orbit 3"]
    assert bob["path_length"] == pytest.approx(1.0, abs=0.05)
    assert animation["motion"]["camera_path_length"] == pytest.approx(1.0, abs=0.01)
    outside = lab["inspections"]["abstract-keys_out_of_range"]["animation"]["objects"][0]
    assert outside["key_range"] == [300.0, 400.0] and outside["keys_after_end"] == 6


def test_lowest_ring_rests_on_the_plinth(lab):
    rings = {
        o["name"]: o
        for o in lab["inspections"]["abstract"]["objects"]
        if o["name"].startswith("Copper orbit")
    }
    lowest = min(rings.values(), key=lambda o: o["bbox_min"][2])
    assert lowest["support"]["surface_below"] == "Exhibition plinth"
    assert lowest["support"]["gap_below"] == pytest.approx(0.002, abs=0.0015)
    assert "Exhibition plinth" in lowest["support"]["touching"]


@pytest.mark.parametrize("name", [*RECIPES, *(f"abstract-{v}" for v in VARIANTS)])
def test_fresh_inspection_reproduces_fixture(lab, name):
    recorded = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert stable_facts(lab["inspections"][name]) == stable_facts(recorded)
