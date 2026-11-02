"""blender_quality.api: the stable integration surface, its JSON Schemas and the live inspection code."""

import ast
import inspect
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from blender_quality import __version__, api
from blender_quality.live import INSPECTOR
from blender_quality.pipeline import check_report

jsonschema = pytest.importorskip("jsonschema")

FIXTURES = Path(__file__).parent / "fixtures"
INSPECTIONS = sorted((FIXTURES / "inspections").glob("*.json"))
PREVIEWS = {p.name.removesuffix("-preview.png"): p for p in (FIXTURES / "renders").glob("*.png")}


def validator(name):
    schema = api.schema(name)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def assert_valid(name, data):
    errors = sorted(validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    assert not errors, [f"{list(e.absolute_path)}: {e.message}" for e in errors[:5]]


# ---------------------------------------------------------------- the API surface is stable


def test_api_version_and_exports():
    assert api.API_VERSION == 1
    assert api.INSPECTION_SCHEMA_VERSION == 2 and api.REPORT_VERSION == 1
    assert api.LIVE_PREFIX == "BQL_INSPECTION_JSON:"
    assert api.version() == __version__
    for name in api.__all__:
        assert hasattr(api, name), name
    assert issubclass(api.BlenderNotFound, api.BlenderError)
    assert issubclass(api.InputError, ValueError)


@pytest.mark.parametrize(
    "function, signature",
    [
        (
            "check",
            "(path, *, output_dir=None, blender=None, subject=None, subject_collection=None, "
            "strict_contact=False, preview=True, timeout=600)",
        ),
        (
            "live_inspection_code",
            "(*, subject=None, subject_collection=None, contact_scale=None, grid=None, samples=None, "
            "animation_samples=None)",
        ),
        ("parse_live_output", "(text)"),
        ("score", "(inspection, strict_contact=False)"),
        ("describe", "(inspection, image_metrics=None, fmt='md', *, strict_contact=False)"),
        ("measure", "(png_path)"),
        ("schema", "(name)"),
        ("schema_path", "(name)"),
        ("blender_info", "(blender=None)"),
    ],
)
def test_signatures_do_not_drift(function, signature):
    """API version 1 promises these signatures; changing one must be deliberate (and documented)."""
    assert str(inspect.signature(getattr(api, function))) == signature


# ---------------------------------------------------------------- schemas


def test_schemas_are_valid_draft_2020_12_and_shipped():
    for name in ("inspection", "report"):
        path = api.schema_path(name)
        assert path.is_file() and path.parent.name == "schemas"
        schema = api.schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(schema)
    with pytest.raises(ValueError, match="unknown schema"):
        api.schema_path("manifest")


@pytest.mark.parametrize("path", INSPECTIONS, ids=lambda p: p.stem)
def test_recorded_inspections_conform(path):
    assert_valid("inspection", json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", INSPECTIONS, ids=lambda p: p.stem)
def test_generated_reports_conform(path):
    inspection = json.loads(path.read_text(encoding="utf-8"))
    preview = PREVIEWS.get(path.stem)
    metrics = api.measure(preview) if preview else None
    files = {
        "inspection": "x/inspection.json",
        "preview": str(preview) if preview else None,
        "technical": "x/technical.json",
        "report_md": "x/report.md",
        "report_json": "x/report.json",
    }
    for strict_contact in (False, True):
        report = check_report(inspection, metrics, strict_contact=strict_contact, files=files)
        assert_valid("report", report)
        assert report["markdown"] == api.describe(inspection, metrics, strict_contact=strict_contact)
        assert report["all_gates_passed"] == all(c["passed"] for c in report["checks"])
    describe_schema = {**api.schema("report")["$defs"]["describe"], "$defs": api.schema("report")["$defs"]}
    errors = list(
        jsonschema.Draft202012Validator(describe_schema).iter_errors(api.describe(inspection, fmt="json"))
    )
    assert not errors, [e.message for e in errors[:5]]


def test_schema_rejects_what_the_gates_would_reject():
    inspection = json.loads((FIXTURES / "inspections" / "abstract.json").read_text(encoding="utf-8"))
    del inspection["lights"]
    assert list(validator("inspection").iter_errors(inspection))
    with pytest.raises(ValueError, match="'lights'"):
        api.score(inspection)


# ---------------------------------------------------------------- pure-Python functions


def test_score_describe_and_measure_accept_dicts_and_paths():
    path = FIXTURES / "inspections" / "abstract-camera_away.json"
    inspection = json.loads(path.read_text(encoding="utf-8"))
    assert api.score(path) == api.score(inspection)
    assert api.score(inspection)["passed"] < api.score(inspection)["total"]
    markdown = api.describe(path)
    assert markdown.startswith("# Scene report: QualityLab_abstract") and "cam.rotation_euler" in markdown
    preview = FIXTURES / "renders" / "abstract-preview.png"
    report = api.describe(inspection, preview, fmt="json")
    assert report["fixes"][0]["id"] == "subject_in_frame"
    assert report["exposure"]["luminance"] == api.measure(preview)["luminance"]
    with pytest.raises(ValueError, match="fmt"):
        api.describe(inspection, fmt="html")
    with pytest.raises(TypeError):
        api.score(42)


# ---------------------------------------------------------------- check (with a fake Blender process)


class FakeBlender:
    def __init__(self, inspection, preview=None, returncode=0):
        self.inspection, self.preview, self.returncode = inspection, preview, returncode
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if self.returncode == 0:
            args = command[command.index("--") + 1 :]
            shutil.copyfile(self.inspection, args[args.index("--output") + 1])
            if self.preview and "--preview" in args:
                shutil.copyfile(self.preview, args[args.index("--preview") + 1])
        return subprocess.CompletedProcess(command, self.returncode, "", "Traceback\nboom\n")


@pytest.fixture
def scene(tmp_path):
    path = tmp_path / "scene.blend"
    path.write_bytes(b"BLENDER")
    return path


def test_check_returns_what_report_json_holds(monkeypatch, tmp_path, scene):
    name = "abstract-no_lights_unused_emission"
    fake = FakeBlender(FIXTURES / "inspections" / f"{name}.json", PREVIEWS[name])
    monkeypatch.setattr(subprocess, "run", fake)
    exe = tmp_path / "blender.exe"
    exe.write_text("fake", encoding="utf-8")
    report = api.check(scene, blender=str(exe), subject="Copper*", subject_collection=["Sculpture"])
    command = fake.calls[0]
    assert command[command.index("--subject") + 1] == "Copper*"
    assert command[command.index("--subject-collection") + 1] == "Sculpture"
    assert "--disable-autoexec" in command and "--preview" in command
    assert report["all_gates_passed"] is False
    assert report["fixes"][0]["python"] and "Nothing lights the subject" in report["markdown"]
    assert report["blender_runtime"] == {"path": str(exe), "kind": "blender", "found_via": "--blender"}
    folder = tmp_path / "scene.quality"
    assert json.loads((folder / "report.json").read_text(encoding="utf-8")) == report
    assert (folder / "report.md").read_text(encoding="utf-8") == report["markdown"]
    assert report["files"]["preview"] == str(folder / "preview.png")
    assert_valid("report", report)


def test_check_without_preview_and_with_output_dir(monkeypatch, tmp_path, scene):
    fake = FakeBlender(FIXTURES / "inspections" / "abstract.json")
    monkeypatch.setattr(subprocess, "run", fake)
    exe = tmp_path / "blender"
    exe.write_text("fake", encoding="utf-8")
    report = api.check(
        scene, blender=str(exe), preview=False, output_dir=tmp_path / "out", strict_contact=True
    )
    assert "--preview" not in fake.calls[0]
    assert report["all_gates_passed"] and report["strict_contact"]
    assert report["files"]["preview"] is None and "exposure" not in report
    assert {c["id"] for c in report["checks"]} >= {"grounded", "camera"}


def test_check_raises_the_blender_error_family(monkeypatch, tmp_path, scene):
    monkeypatch.setattr(subprocess, "run", FakeBlender(None, returncode=1))
    exe = tmp_path / "blender"
    exe.write_text("fake", encoding="utf-8")
    with pytest.raises(api.BlenderError, match="exited with code 1") as info:
        api.check(scene, blender=str(exe))
    assert info.value.output_tail == ["Traceback", "boom"]
    with pytest.raises(api.BlenderNotFound):
        api.check(scene, blender=str(tmp_path / "missing" / "blender"))
    with pytest.raises(api.InputError, match="does not exist"):
        api.check(tmp_path / "missing.blend", blender=str(exe))
    assert not (tmp_path / "missing.quality").exists()


# ---------------------------------------------------------------- live inspection code


def test_live_code_is_self_contained_python():
    code = api.live_inspection_code(subject_collection="ASTRA", contact_scale=2, animation_samples=0)
    tree = ast.parse(code)
    # Only the embedded inspector source (a string) and a few top-level statements; nothing from
    # this package, no __file__ and no sys.argv at the top level.
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert names <= {"_bql_namespace", "exec", "compile", "print"}
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    embedded = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert INSPECTOR.read_text(encoding="utf-8") in embedded
    compile(code, "<live>", "exec")
    dicts = [ast.literal_eval(n) for n in ast.walk(tree) if isinstance(n, ast.Dict)]
    assert {"__name__": "blender_quality_live_inspection"} in dicts  # a private namespace
    options = next(d for d in dicts if "subject" in d)
    assert options == {
        "subject": [],
        "subject_collection": ["ASTRA"],
        "contact_scale": 2.0,
        "animation_samples": 0,
    }
    assert code.isascii()


def test_live_code_validates_options():
    with pytest.raises(TypeError):
        api.live_inspection_code(subject=3)
    with pytest.raises(TypeError):
        api.live_inspection_code(grid=12.5)
    with pytest.raises(ValueError):
        api.live_inspection_code(contact_scale=0)
    with pytest.raises(ValueError):
        api.live_inspection_code(animation_samples=-1)
    with pytest.raises(TypeError):
        api.live_inspection_code(subject_collection=["ASTRA", None])


def test_parse_live_output():
    inspection = json.loads((FIXTURES / "inspections" / "abstract.json").read_text(encoding="utf-8"))
    line = api.LIVE_PREFIX + json.dumps(inspection, separators=(",", ":"))
    assert api.parse_live_output(line + "\n") == inspection
    # As a harness relays it (Blender MCP's execute_code result, other prints around it).
    relayed = "Info: something\nCode executed successfully: " + line + "\n"
    assert api.parse_live_output(relayed) == inspection
    assert api.parse_live_output(relayed.encode("utf-8")) == inspection
    with pytest.raises(ValueError, match="no BQL_INSPECTION_JSON: line"):
        api.parse_live_output("Code executed successfully: ")
    with pytest.raises(ValueError, match="2 BQL_INSPECTION_JSON: lines"):
        api.parse_live_output(line + "\n" + line)
    with pytest.raises(ValueError, match="not valid JSON"):
        api.parse_live_output(api.LIVE_PREFIX + "{broken")
    with pytest.raises(ValueError, match="schema_version 2"):
        api.parse_live_output(api.LIVE_PREFIX + '{"schema_version": 1}')
