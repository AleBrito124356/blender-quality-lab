"""Stable integration API for harnesses and CI (API_VERSION 1).

Within API version 1 these names keep their signatures and meaning. Later 1.x releases may add
optional keyword arguments, new keys in returned dicts and new warnings or fixes; they will not
remove or rename keys. A breaking change raises API_VERSION. Python 3.11+, no runtime dependencies.

    from blender_quality import api

    report = api.check("scene.blend", subject_collection="ASTRA")      # isolated Blender or bpy
    if not report["all_gates_passed"]:
        for fix in report["fixes"]:
            print(fix["problem"], fix["python"])

    code = api.live_inspection_code(subject_collection="ASTRA")        # for a running Blender
    inspection = api.parse_live_output(output_of_running(code))
    print(api.describe(inspection))

Failures to find or run Blender raise BlenderError (BlenderNotFound when nothing usable was found);
bad input raises InputError (a ValueError) or ValueError for an invalid inspection.
"""

import os
from pathlib import Path

from . import __version__
from . import describe as _describe
from .image_metrics import measure_file
from .live import PREFIX as LIVE_PREFIX
from .live import live_inspection_code, parse_live_output
from .pipeline import REPORT_VERSION, InputError, check_scene, read_json
from .runner import (
    DEFAULT_TIMEOUT,
    KIND_BLENDER,
    KIND_BPY,
    BlenderError,
    BlenderNotFound,
    blender_version,
    find_blender,
)
from .scoring import technical_report

API_VERSION = 1
INSPECTION_SCHEMA_VERSION = 2
SCHEMAS = {
    "inspection": Path(__file__).parent / "schemas" / "inspection-v2.schema.json",
    "report": Path(__file__).parent / "schemas" / "report-v1.schema.json",
}

__all__ = [
    "API_VERSION",
    "INSPECTION_SCHEMA_VERSION",
    "KIND_BLENDER",
    "KIND_BPY",
    "LIVE_PREFIX",
    "REPORT_VERSION",
    "BlenderError",
    "BlenderNotFound",
    "InputError",
    "blender_info",
    "check",
    "describe",
    "live_inspection_code",
    "measure",
    "parse_live_output",
    "schema",
    "schema_path",
    "score",
    "version",
]


def version():
    """The installed blender-quality-lab version, e.g. '0.3.0'."""
    return __version__


def check(
    path,
    *,
    output_dir=None,
    blender=None,
    subject=None,
    subject_collection=None,
    strict_contact=False,
    preview=True,
    timeout=DEFAULT_TIMEOUT,
):
    """Exactly what `blender-quality check` does; returns the report dict (`check --json`).

    Opens `path` in an isolated background Blender (a Blender executable or a Python with bpy,
    found like the command line finds it, or `blender`), inspects it, renders a small preview
    unless preview=False, measures it, scores the gates and writes inspection.json, preview.png,
    technical.json, report.md and report.json to `output_dir` (default: SCENE.quality/).

    The report holds: all_gates_passed, checks (every gate), failed_gates, warnings, fixes (each
    with priority, problem, action and a Blender Python snippet or None), markdown (report.md),
    files, and the scene facts of `describe`. See schemas/report-v1.schema.json.
    `subject` / `subject_collection` take a name (glob for objects) or a list of them.
    """
    return check_scene(
        path,
        output_dir=output_dir,
        blender=blender,
        subject=subject,
        subject_collection=subject_collection,
        strict_contact=strict_contact,
        preview=preview,
        timeout=timeout,
    )


def _inspection(inspection):
    if isinstance(inspection, dict):
        return inspection
    if isinstance(inspection, (str, os.PathLike)):
        return read_json(inspection)
    raise TypeError("inspection must be a dict or the path of an inspection JSON file")


def score(inspection, strict_contact=False):
    """Technical gates and warnings for an inspection (dict or JSON path), as `score` prints them."""
    return technical_report(_inspection(inspection), strict_contact=strict_contact)


def describe(inspection, image_metrics=None, fmt="md", *, strict_contact=False):
    """The text report for an inspection: Markdown (fmt="md", a str) or the report dict (fmt="json").

    image_metrics is the dict from measure() or the path of a rendered PNG to measure.
    """
    if fmt not in {"md", "json"}:
        raise ValueError("fmt must be 'md' or 'json'")
    if isinstance(image_metrics, (str, os.PathLike)):
        image_metrics = measure_file(image_metrics)
    report = _describe.describe(_inspection(inspection), image_metrics, strict_contact=strict_contact)
    return _describe.to_markdown(report) if fmt == "md" else report


def measure(png_path):
    """Exposure and layout metrics of a rendered PNG (pure Python), as `measure` prints them."""
    return measure_file(png_path)


def schema_path(name):
    """Path of the shipped JSON Schema (draft 2020-12): 'inspection' (v2) or 'report' (v1)."""
    if name not in SCHEMAS:
        raise ValueError(f"unknown schema {name!r}; choose from {', '.join(SCHEMAS)}")
    return SCHEMAS[name]


def schema(name):
    """The shipped JSON Schema as a dict: 'inspection' (v2) or 'report' (v1)."""
    return read_json(schema_path(name))


def blender_info(blender=None):
    """Which Blender would be used and how it was found, as `doctor --json` reports it.

    Returns {"blender": path, "kind": "blender" | "bpy", "found_via": ..., "version": ...};
    raises BlenderNotFound or BlenderError when there is none or it does not answer.
    """
    location = find_blender(blender)
    return {
        "blender": location.path,
        "kind": location.kind,
        "found_via": location.source,
        "version": blender_version(location),
    }
