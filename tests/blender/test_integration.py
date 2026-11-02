"""End-to-end checks against a real Blender. Run with `python -m pytest -m blender`.

"Blender" is whatever blender-quality finds: a Blender executable, or a Python interpreter that can
import bpy (`BLENDER=/path/to/python python -m pytest -m blender`). Builds the three recipes,
derives the sabotaged variants with sabotage.py, inspects everything through the CLI (isolated
Blender) and compares with the recorded fixtures in tests/fixtures, which the pure-Python tests use
without Blender. Set BQL_UPDATE_FIXTURES=1 to re-record them.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from blender_quality import cli
from blender_quality.describe import describe
from blender_quality.image_metrics import measure_file
from blender_quality.runner import (
    KIND_BPY,
    BlenderError,
    blender_version,
    find_blender,
    isolated_env,
    run_blender,
)
from blender_quality.scoring import technical_report

pytestmark = pytest.mark.blender
HERE = Path(__file__).parent
FIXTURES = HERE.parent / "fixtures" / "inspections"
RENDERS = HERE.parent / "fixtures" / "renders"
PREVIEWS = {
    "abstract": [],
    "abstract-no_lights_unused_emission": ["black_frame"],
    "abstract-hidden_collection": ["underexposed", "near_uniform"],
}
RECIPES = ["product", "abstract", "interior"]
VARIANTS = {
    "camera_away": {"subject_in_frame"},
    "floating": set(),
    "hidden_collection": {"renderable_geometry"},
    "zero_scale_parent": {"non_degenerate_world_transform"},
    "no_lights_unused_emission": {"effective_illumination"},
    "relight": set(),
    "animated": set(),
    "keys_out_of_range": {"animation_keys_in_range"},
    "no_camera": {"camera"},
    "pano_camera": set(),
    "empty": {"renderable_geometry", "camera"},
}

try:
    BLENDER = find_blender()  # a BlenderLocation: a Blender executable or a bpy interpreter
except BlenderError:
    BLENDER = None
BLENDER_PATH = BLENDER.path if BLENDER else None


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    root = tmp_path_factory.mktemp("lab")
    scenes = {}
    for recipe in RECIPES:
        assert cli.main(["build", recipe, "--output", str(root / recipe), "--blender", BLENDER_PATH]) == 0
        scenes[recipe] = root / recipe / f"{recipe}.blend"
    for variant in VARIANTS:
        target = root / f"abstract-{variant}.blend"
        run_blender(BLENDER, HERE / "sabotage.py", [target, variant], blend_file=scenes["abstract"])
        scenes[f"abstract-{variant}"] = target
    inspections, previews = {}, {}
    update = os.environ.get("BQL_UPDATE_FIXTURES") == "1"
    for name, blend in scenes.items():
        output = root / f"{name}.json"
        command = ["inspect", str(blend), "--output", str(output), "--blender", BLENDER_PATH]
        if name in PREVIEWS:
            previews[name] = root / f"{name}-preview.png"
            command += [
                "--preview",
                str(previews[name]),
                "--preview-percentage",
                "20",
                "--preview-samples",
                "8",
            ]
        assert cli.main(command) == 0
        inspections[name] = json.loads(output.read_text(encoding="utf-8"))
        if update:
            FIXTURES.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output, FIXTURES / f"{name}.json")
            if name in previews:
                RENDERS.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(previews[name], RENDERS / f"{name}-preview.png")
    return {"root": root, "scenes": scenes, "inspections": inspections, "previews": previews}


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
    assert primary_failures(technical_report(inspection)) == VARIANTS[variant]
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


@pytest.mark.parametrize("name", PREVIEWS)
def test_preview_render_is_measured(lab, name):
    metrics = measure_file(lab["previews"][name])
    assert (metrics["width"], metrics["height"]) == (192, 144)
    assert [w["id"] for w in metrics["warnings"]] == PREVIEWS[name]
    assert lab["inspections"][name]["preview"]["percentage"] == 20


@pytest.mark.parametrize(
    "variant",
    [
        "camera_away",
        "floating",
        "hidden_collection",
        "zero_scale_parent",
        "no_lights_unused_emission",
        "keys_out_of_range",
        "no_camera",
    ],
)
def test_describe_fixes_repair_the_scene(lab, variant, tmp_path):
    """Apply every Python fix `describe` suggests inside Blender; the repaired scene must pass all gates."""
    name = f"abstract-{variant}"
    report = describe(lab["inspections"][name], strict_contact=True)
    snippets = [item["python"] for item in report["fixes"] if item["python"]]
    assert snippets, report["fixes"]
    fixes = tmp_path / "fixes.json"
    fixes.write_text(json.dumps(snippets), encoding="utf-8")
    repaired = tmp_path / f"{name}-fixed.blend"
    run_blender(BLENDER, HERE / "apply_fixes.py", [fixes, repaired], blend_file=lab["scenes"][name])
    output = tmp_path / "fixed.json"
    assert cli.main(["inspect", str(repaired), "--output", str(output), "--blender", BLENDER_PATH]) == 0
    result = technical_report(json.loads(output.read_text(encoding="utf-8")), strict_contact=True)
    assert result["passed"] == result["total"], [c for c in result["checks"] if not c["passed"]]


@pytest.mark.parametrize("variant", ["no_camera", "pano_camera", "empty"])
def test_check_survives_scenes_that_cannot_be_framed(lab, variant, tmp_path):
    scene = lab["scenes"][f"abstract-{variant}"]
    output = tmp_path / "quality"
    assert cli.main(["check", str(scene), "--output-dir", str(output), "--blender", BLENDER_PATH]) == 0
    inspection = json.loads((output / "inspection.json").read_text(encoding="utf-8"))
    assert (output / "report.md").read_text(encoding="utf-8").startswith("# Scene report")
    if variant == "pano_camera":
        assert (output / "preview.png").is_file()
    else:
        assert inspection["preview"]["skipped"] == "the scene has no active camera"
        assert not (output / "preview.png").exists()


# ---------------------------------------------------------------- runtime and isolation, both kinds


def test_doctor_names_the_runtime(capsys):
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    assert cli.main(["doctor", "--json", "--blender", BLENDER_PATH]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == BLENDER.kind
    assert re.match(r"Blender \d+\.\d+", report["version"])


def plant_user_startup_script(home, version, canary):
    """A startup script in every per-user Blender folder (Linux, macOS, Windows) for this HOME."""
    script = f"open({canary.as_posix()!r}, 'w').write('user startup script ran')\n"
    script += "def register():\n    pass\n\ndef unregister():\n    pass\n"
    folders = [
        home / "xdg" / "blender" / version,
        home / "home" / ".config" / "blender" / version,
        home / "home" / "Library" / "Application Support" / "Blender" / version,
        home / "appdata" / "Blender Foundation" / "Blender" / version,
    ]
    for folder in folders:
        (folder / "scripts" / "startup").mkdir(parents=True)
        (folder / "scripts" / "startup" / "bql_user_canary.py").write_text(script, encoding="utf-8")
    return {
        "HOME": str(home / "home"),
        "XDG_CONFIG_HOME": str(home / "xdg"),
        "APPDATA": str(home / "appdata"),
    }


def test_user_config_and_overrides_are_never_loaded(lab, tmp_path, monkeypatch):
    version = re.match(r"Blender (\d+\.\d+)", blender_version(BLENDER)).group(1)
    canary = tmp_path / "user-canary.txt"
    env = plant_user_startup_script(tmp_path / "user", version, canary)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    system_scripts = tmp_path / "system" / "startup"
    system_scripts.mkdir(parents=True)
    (system_scripts / "bql_system_canary.py").write_text(
        f"open({(tmp_path / 'system-canary.txt').as_posix()!r}, 'w').write('ran')\n", encoding="utf-8"
    )
    monkeypatch.setenv("BLENDER_SYSTEM_SCRIPTS", str(tmp_path / "system"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "pythonpath"))

    probe = tmp_path / "probe.json"
    run_blender(
        BLENDER, HERE / "probe_isolation.py", [probe, "a b", "--flag"], blend_file=lab["scenes"]["abstract"]
    )
    data = json.loads(probe.read_text(encoding="utf-8"))
    assert not canary.exists() and not (tmp_path / "system-canary.txt").exists()
    assert data["background"] and data["factory_startup"] and not data["autoexec_preference"]
    assert data["arguments"] == [str(probe), "a b", "--flag"]
    assert data["argv"][data["argv"].index("--") - 2 :][:2] == ["--python", str(HERE / "probe_isolation.py")]
    assert "--disable-autoexec" in data["argv"] and data["name"] == "__main__"
    assert not any(str(tmp_path) in path for path in data["script_paths"])
    assert "BLENDER_SYSTEM_SCRIPTS" not in data["blender_variables"]
    if BLENDER.kind == KIND_BPY:
        # python -I: PYTHONPATH and the user site-packages are ignored, as Blender ignores them.
        assert data["python_flags"] == {"isolated": 1, "ignore_environment": 1, "no_user_site": 1}
        # Control: imported directly, bpy would use the planted per-user folder ...
        plain = subprocess.run(
            [BLENDER.path, "-I", "-c", "import bpy; print(bpy.utils.resource_path('USER'))"],
            capture_output=True,
            text=True,
            env=isolated_env(),
            check=True,
        )
        assert plain.stdout.strip().startswith(str(tmp_path / "user"))
        # ... while the launcher points it at an empty temporary folder.
        assert not data["user_resources"].startswith(str(tmp_path))
    else:
        # Control: without --factory-startup the same Blender does run the planted script.
        subprocess.run(
            [BLENDER.path, "--background", "--python-expr", "pass"],
            env=isolated_env(),
            timeout=300,
            check=False,
        )
        assert canary.exists()


def test_python_in_the_blend_never_runs(lab, tmp_path):
    """Registered text blocks and scripted drivers stay inert in inspect and check (preview render)."""
    canaries = tmp_path / "canaries"
    canaries.mkdir()
    scene = tmp_path / "canary.blend"
    run_blender(
        BLENDER, HERE / "make_autoexec_canary.py", [scene, canaries], blend_file=lab["scenes"]["abstract"]
    )
    output = tmp_path / "quality"
    command = ["check", str(scene), "--output-dir", str(output), "--blender", BLENDER_PATH]
    assert cli.main([*command, "--preview-percentage", "10", "--preview-samples", "1"]) == 0
    assert list(canaries.iterdir()) == []
    inspection = json.loads((output / "inspection.json").read_text(encoding="utf-8"))
    assert inspection["animation"]["python_drivers_not_evaluated"] == 1
    # Control: the same file with autoexec allowed runs both pieces of embedded Python.
    if BLENDER.kind == KIND_BPY:
        code = (
            "import bpy, sys; bpy.context.preferences.filepaths.use_scripts_auto_execute = True; "
            "bpy.ops.wm.open_mainfile(filepath=sys.argv[1], use_scripts=True); "
            "bpy.context.evaluated_depsgraph_get(); "
            "import os; os._exit(0)"  # bpy 4.5 can hang in its exit after a driver ran (see bpy_launcher.py)
        )
        control = [BLENDER.path, "-I", "-c", code, str(scene)]
    else:
        expr = "import bpy; bpy.context.evaluated_depsgraph_get()"
        control = [BLENDER.path, "--background", "--factory-startup", "--enable-autoexec", str(scene)]
        control += ["--python-expr", expr]
    subprocess.run(control, env=isolated_env(), capture_output=True, timeout=300, check=False)
    assert sorted(p.name for p in canaries.iterdir()) == ["driver.txt", "text-block.txt"]


@pytest.mark.parametrize(
    "mode, message",
    [("raise", "RuntimeError: boom from the test script"), ("exit", "stopped by the test script")],
)
def test_script_failures_exit_non_zero_with_the_error_tail(mode, message):
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    with pytest.raises(BlenderError) as info:
        run_blender(BLENDER, HERE / "script_failures.py", [mode], timeout=300)
    assert info.value.returncode == 1
    assert message in info.value.output_tail[-1]
    assert str(info.value).endswith("exited with code 1 while running script_failures.py")


def test_timeout_stops_a_stuck_script():
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    with pytest.raises(BlenderError, match="did not finish within 5 s"):
        run_blender(BLENDER, HERE / "script_failures.py", ["sleep"], timeout=5)


def test_unreadable_blend_is_an_error_not_an_empty_scene(tmp_path):
    if BLENDER is None:
        pytest.skip("Blender is not installed")
    broken = tmp_path / "broken.blend"
    broken.write_bytes(b"this is not a blend file")
    with pytest.raises(BlenderError):
        run_blender(
            BLENDER, HERE / "probe_datablocks.py", [tmp_path / "x.json"], blend_file=broken, timeout=300
        )
    assert not (tmp_path / "x.json").exists()
