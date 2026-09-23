"""Regenerate examples/runs from real, offline Blender runs (no model, no API).

    python examples/make_example_runs.py            # needs Blender (found like the CLI finds it)

Layout written: examples/runs/<config>/<brief>/<run>/{manifest.json, technical.json, report.md}.

- procedural-recipes: each lab recipe built and inspected three times for the brief it answers.
  Builds are deterministic, so the three runs agree; that is the baseline to compare harness runs to.
- sabotaged-recipes: the copper-orbits recipe with one scripted defect per run (tests/blender/sabotage.py),
  plus one run stopped by a real 0.5 s --timeout, so failures and timeouts show up in the summary.

manifest.json uses the Astra Blender Harness keys (status, model, steps, total_tokens,
elapsed_seconds). No human ratings are included: they would have to be invented.
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from blender_quality.cli import main as cli
from blender_quality.describe import describe, to_markdown
from blender_quality.runner import BlenderError, find_blender, run_blender
from blender_quality.scoring import technical_report

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "examples" / "runs"
SABOTAGE = ROOT / "tests" / "blender" / "sabotage.py"
RECIPES = {"ceramic-lamp": "product", "copper-orbits": "abstract", "reading-nook": "interior"}
STRICT = {"ceramic-lamp", "copper-orbits", "reading-nook"}


def write_run(folder, manifest, inspection, strict_contact):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if inspection is not None:
        report = technical_report(inspection, strict_contact=strict_contact)
        (folder / "technical.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        text = to_markdown(describe(inspection, strict_contact=strict_contact))
        (folder / "report.md").write_text(text, encoding="utf-8", newline="\n")


def inspect(blend, output, blender, timeout=600):
    code = cli(
        ["inspect", str(blend), "--output", str(output), "--blender", blender, "--timeout", str(timeout)]
    )
    if code != 0:
        raise BlenderError(f"inspect exited with {code}")
    return json.loads(output.read_text(encoding="utf-8"))


def main():
    blender = find_blender().path
    if RUNS.exists():
        shutil.rmtree(RUNS)
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        for brief, recipe in RECIPES.items():
            for index in range(1, 4):
                started = time.perf_counter()
                out = scratch / f"{recipe}-{index}"
                assert cli(["build", recipe, "--output", str(out), "--blender", blender]) == 0
                inspection = inspect(out / f"{recipe}.blend", out / "inspection.json", blender)
                manifest = {
                    "schema_version": 1,
                    "status": "completed",
                    "model": "none (procedural lab recipe)",
                    "steps": 0,
                    "total_tokens": 0,
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "note": f"`blender-quality build {recipe}` then `inspect`",
                }
                write_run(
                    RUNS / "procedural-recipes" / brief / f"run-{index}",
                    manifest,
                    inspection,
                    brief in STRICT,
                )
        base = scratch / "abstract-1" / "abstract.blend"
        for variant in ["camera_away", "floating", "no_lights_unused_emission"]:
            started = time.perf_counter()
            target = scratch / f"abstract-{variant}.blend"
            run_blender(blender, SABOTAGE, [target, variant], blend_file=base)
            inspection = inspect(target, scratch / f"{variant}.json", blender)
            manifest = {
                "schema_version": 1,
                "status": "completed",
                "model": f"none (copper-orbits recipe + scripted defect '{variant}')",
                "steps": 0,
                "total_tokens": 0,
                "elapsed_seconds": round(time.perf_counter() - started, 2),
            }
            write_run(RUNS / "sabotaged-recipes" / "copper-orbits" / variant, manifest, inspection, True)
        started = time.perf_counter()
        script = ROOT / "src" / "blender_quality" / "scripts" / "inspect_scene.py"
        try:
            run_blender(blender, script, ["--output", scratch / "timeout.json"], blend_file=base, timeout=0.5)
            status, error = "completed", None
        except BlenderError as exc:
            status, error = "timeout", str(exc)
        manifest = {
            "schema_version": 1,
            "status": status,
            "model": "none (inspection stopped by --timeout 0.5)",
            "steps": 0,
            "total_tokens": 0,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "error": error,
        }
        write_run(RUNS / "sabotaged-recipes" / "copper-orbits" / "timeout", manifest, None, True)
    print(f"wrote {RUNS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
