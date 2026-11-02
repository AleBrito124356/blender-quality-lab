"""Inspect the scene of an already running Blender, for harnesses that send Python to it (e.g. MCP).

`live_inspection_code()` returns self-contained Python source: the inspector (scripts/inspect_scene.py)
embedded as a string literal and executed in a private namespace, followed by one call that prints

    BQL_INSPECTION_JSON:{...inspection schema 2...}

It needs only what a running Blender provides (bpy, mathutils, numpy). It does not use __file__,
sys.argv or this package, opens no file and never saves. It changes viewport visibility to mirror
render visibility and steps through frames to sample animation; both are restored before it
returns, also on error. `parse_live_output()` reads the printed line back.
"""

import json
import math
from pathlib import Path

from . import __version__

PREFIX = "BQL_INSPECTION_JSON:"
INSPECTOR = Path(__file__).parent / "scripts" / "inspect_scene.py"

TEMPLATE = """\
# blender-quality-lab {version}: live scene inspection (inspection schema 2).
# Inspects the current scene of this running Blender. Opens no file, reads no argv and never saves;
# viewport visibility and the current frame are changed temporarily and restored.
# Prints exactly one line: {prefix}{{...}}
_bql_namespace = {{"__name__": "blender_quality_live_inspection"}}
try:
    exec(compile({source}, "<blender-quality-lab inspect_scene.py>", "exec"), _bql_namespace)
    print(_bql_namespace["live_inspection_line"](**{options}))
finally:
    del _bql_namespace
"""


def _positive(name, value, kind, minimum):
    if isinstance(value, bool) or not isinstance(value, kind):
        raise TypeError(f"{name} must be {'an integer' if kind is int else 'a number'}")
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _names(name, value):
    if value is None:
        return []
    values = [value] if isinstance(value, str) else list(value)
    if not all(isinstance(v, str) and v for v in values):
        raise TypeError(f"{name} must be a non-empty string or a list of them")
    return values


def live_options(
    *,
    subject=None,
    subject_collection=None,
    contact_scale=None,
    grid=None,
    samples=None,
    animation_samples=None,
):
    """Validated keyword arguments for the inspector's live_inspection()."""
    options = {
        "subject": _names("subject", subject),
        "subject_collection": _names("subject_collection", subject_collection),
    }
    if contact_scale is not None:
        options["contact_scale"] = float(_positive("contact_scale", contact_scale, (int, float), 1e-9))
    if grid is not None:
        options["grid"] = _positive("grid", grid, int, 4)
    if samples is not None:
        options["samples"] = _positive("samples", samples, int, 1)
    if animation_samples is not None:
        options["animation_samples"] = _positive("animation_samples", animation_samples, int, 0)
    return options


def live_inspection_code(
    *,
    subject=None,
    subject_collection=None,
    contact_scale=None,
    grid=None,
    samples=None,
    animation_samples=None,
):
    """Python source to exec inside a running Blender; it prints one BQL_INSPECTION_JSON line.

    subject / subject_collection: object name or glob / collection name (a string or a list), as
    `inspect --subject/--subject-collection`; by default the subject is chosen by the same heuristic.
    contact_scale multiplies the 5 mm contact tolerance; grid is the object-ID grid width (64);
    samples the surface samples per object (256); animation_samples the frames sampled for motion
    (24; 0 or 1 skips motion sampling and so never changes the current frame).
    """
    options = live_options(
        subject=subject,
        subject_collection=subject_collection,
        contact_scale=contact_scale,
        grid=grid,
        samples=samples,
        animation_samples=animation_samples,
    )
    source = INSPECTOR.read_text(encoding="utf-8")
    return TEMPLATE.format(version=__version__, prefix=PREFIX, source=ascii(source), options=repr(options))


def parse_live_output(text):
    """The inspection dict from the output of live_inspection_code (stdout, possibly with other lines)."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if not isinstance(text, str):
        raise TypeError("parse_live_output needs the captured output as a string")
    found = [line[line.index(PREFIX) + len(PREFIX) :] for line in text.splitlines() if PREFIX in line]
    if not found:
        raise ValueError(f"no {PREFIX} line in the output; did the code run inside Blender?")
    if len(found) > 1:
        raise ValueError(f"{len(found)} {PREFIX} lines in the output; pass the output of one run")
    try:
        data = json.loads(found[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"the {PREFIX} line is not valid JSON ({exc.msg} at column {exc.colno})") from None
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise ValueError(f"the {PREFIX} line is not an inspection with schema_version 2")
    return data
