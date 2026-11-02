"""The inspect and check pipelines, shared by the command line and blender_quality.api.

Blender runs only through runner.run_blender (isolated, with a timeout). Everything after the
inspection (gates, render metrics, the report) is pure Python.
"""

import json
from pathlib import Path

from . import __version__
from .describe import describe, to_markdown
from .image_metrics import measure_file
from .runner import DEFAULT_TIMEOUT, BlenderError, BlenderLocation, find_blender, run_blender
from .scoring import technical_report

SCRIPTS = Path(__file__).parent / "scripts"
REPORT_VERSION = 1
CHECK_FILES = ("inspection.json", "preview.png", "technical.json", "report.md", "report.json")


class InputError(ValueError):
    """Bad input from the caller (missing file, invalid JSON); the command line exits with code 2."""


def read_json(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"{path}: file not found") from None
    except OSError as exc:
        raise InputError(f"{path}: cannot read ({exc.strerror or exc})") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(
            f"{path}: not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})"
        ) from None


def names_list(value):
    """None, one name or an iterable of names -> list of names."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    names = list(value)
    if not all(isinstance(name, str) for name in names):
        raise InputError("subject and subject collection names must be strings")
    return names


def inspection_args(subject=(), subject_collection=(), scene_name=None, grid=64, contact_scale=1.0):
    """Options forwarded to scripts/inspect_scene.py."""
    extra = []
    for name in names_list(subject):
        extra += ["--subject", name]
    for name in names_list(subject_collection):
        extra += ["--subject-collection", name]
    if scene_name:
        extra += ["--scene", scene_name]
    return extra + ["--grid", str(grid), "--contact-scale", str(contact_scale)]


def locate(blender):
    """A BlenderLocation as given, or discovered from a path/None like the command line does."""
    return blender if isinstance(blender, BlenderLocation) else find_blender(blender)


def run_inspection(
    scene,
    output,
    *,
    blender=None,
    preview=None,
    preview_percentage=25,
    preview_samples=16,
    timeout=DEFAULT_TIMEOUT,
    verbose=False,
    **options,
):
    """Inspect a .blend in an isolated Blender; write the inspection JSON (and the preview PNG).

    `options` are subject, subject_collection, scene_name, grid and contact_scale.
    Returns (BlenderLocation, BlenderRun).
    """
    location = locate(blender)
    scene = Path(scene)
    if not scene.is_file():
        raise InputError(f"Scene file does not exist: {scene}")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    script_args = ["--output", output.resolve(), *inspection_args(**options)]
    if preview is not None:
        script_args += [
            "--preview",
            Path(preview).resolve(),
            "--preview-percentage",
            str(preview_percentage),
            "--preview-samples",
            str(preview_samples),
        ]
    run = run_blender(
        location,
        SCRIPTS / "inspect_scene.py",
        script_args,
        blend_file=scene.resolve(),
        timeout=timeout,
        verbose=verbose,
    )
    if not output.is_file():
        raise BlenderError(f"{location.label} finished but did not write the inspection JSON")
    return location, run


def check_report(inspection, metrics=None, *, strict_contact=False, files=None, runtime=None):
    """The `check` report: the `describe` report plus every gate, the Markdown text and the files.

    This is what `check --json` prints, what `check` saves as report.json and what
    blender_quality.api.check returns (schemas/report-v1.schema.json).
    """
    technical = technical_report(inspection, strict_contact=strict_contact)
    described = describe(inspection, metrics, strict_contact=strict_contact)
    report = {
        "kind": "check",
        "report_version": REPORT_VERSION,
        "lab_version": __version__,
        "all_gates_passed": technical["passed"] == technical["total"],
        "strict_contact": bool(strict_contact),
        **described,
        "checks": technical["checks"],
        "preview": inspection.get("preview"),
        "files": dict(files or {}),
        "blender_runtime": runtime,
    }
    report["markdown"] = to_markdown(described)
    return report


def check_scene(
    scene,
    *,
    output_dir=None,
    blender=None,
    preview=True,
    strict_contact=False,
    preview_percentage=25,
    preview_samples=16,
    timeout=DEFAULT_TIMEOUT,
    verbose=False,
    **options,
):
    """Inspect + preview render + measure + gates + report, as `blender-quality check` does.

    Writes inspection.json, preview.png, technical.json, report.md and report.json into
    `output_dir` (default: SCENE.quality/ next to the scene) and returns the check report.
    """
    scene = Path(scene)
    if not scene.is_file():
        raise InputError(f"Scene file does not exist: {scene}")
    output_dir = Path(output_dir) if output_dir else scene.with_name(scene.stem + ".quality")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: output_dir / name for name in CHECK_FILES}
    for stale in CHECK_FILES:
        paths[stale].unlink(missing_ok=True)  # never measure or report a previous run's files
    location, _run = run_inspection(
        scene,
        paths["inspection.json"],
        blender=blender,
        preview=paths["preview.png"] if preview else None,
        preview_percentage=preview_percentage,
        preview_samples=preview_samples,
        timeout=timeout,
        verbose=verbose,
        **options,
    )
    preview_file = paths["preview.png"] if preview and paths["preview.png"].is_file() else None
    metrics = measure_file(preview_file) if preview_file is not None else None
    inspection = read_json(paths["inspection.json"])
    files = {
        "inspection": str(paths["inspection.json"]),
        "preview": str(preview_file) if preview_file is not None else None,
        "technical": str(paths["technical.json"]),
        "report_md": str(paths["report.md"]),
        "report_json": str(paths["report.json"]),
    }
    runtime = {"path": location.path, "kind": location.kind, "found_via": location.source}
    report = check_report(inspection, metrics, strict_contact=strict_contact, files=files, runtime=runtime)
    technical = technical_report(inspection, strict_contact=strict_contact)
    paths["technical.json"].write_text(json.dumps(technical, indent=2), encoding="utf-8")
    paths["report.md"].write_text(report["markdown"], encoding="utf-8")
    paths["report.json"].write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
